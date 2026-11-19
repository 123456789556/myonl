/* ===================================================================
   在浏览器里给 APK 打 v2 签名（P171）
   -------------------------------------------------------------------
   为什么要在前端做：手机上没有 Java，跑不了 apksigner。但 v2 的本质
   只有三步 —— 算摘要、RSA 签名、拼一段字节。WebCrypto 全都能提供。
   以前说"手机做不了 APK"，是把"跑不了构建链"错当成了"签不了名"。

   摘要规则（source.android.com 原文，别凭记忆改）：
     每段切成 1 MB，最后一块可以短
     每块   SHA256(0xa5 || u32(块长) || 块内容)
     总摘要 SHA256(0x5a || u32(总块数) || 各块摘要顺序拼接)
     三个段（条目区 / 中央目录 / EOCD）的块**连成一条链**，只出一个摘要
     EOCD 里"中央目录偏移"字段要按签名块起点算
   =================================================================== */
(function (global) {
  "use strict";

  const CHUNK = 1 << 20;
  const SIG_ALG = 0x0103;          // RSASSA-PKCS1-v1_5 + SHA-256
  const V2_ID = 0x7109871a;
  const GAME_ENTRY = "assets/game.html";

  // ---------- 基础读写 ----------
  const u32 = (n) => { const b = new Uint8Array(4); new DataView(b.buffer).setUint32(0, n, true); return b; };
  const u64 = (n) => { const b = new Uint8Array(8); new DataView(b.buffer).setBigUint64(0, BigInt(n), true); return b; };
  const rd32 = (a, o) => new DataView(a.buffer, a.byteOffset).getUint32(o, true);
  const rd64 = (a, o) => Number(new DataView(a.buffer, a.byteOffset).getBigUint64(o, true));
  const rd16 = (a, o) => new DataView(a.buffer, a.byteOffset).getUint16(o, true);

  function concat(parts) {
    let n = 0;
    for (const p of parts) n += p.length;
    const out = new Uint8Array(n);
    let o = 0;
    for (const p of parts) { out.set(p, o); o += p.length; }
    return out;
  }

  // ---------- CRC32 ----------
  let crcTable = null;
  function crc32(bytes) {
    if (!crcTable) {
      crcTable = new Uint32Array(256);
      for (let i = 0; i < 256; i++) {
        let c = i;
        for (let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
        crcTable[i] = c >>> 0;
      }
    }
    let c = 0xFFFFFFFF;
    for (let i = 0; i < bytes.length; i++) c = crcTable[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8);
    return (c ^ 0xFFFFFFFF) >>> 0;
  }

  // ---------- ZIP 解析 ----------
  function findEocd(bytes) {
    for (let i = bytes.length - 22; i >= 0; i--) {
      if (bytes[i] === 0x50 && bytes[i + 1] === 0x4B && bytes[i + 2] === 0x05 && bytes[i + 3] === 0x06) return i;
    }
    throw new Error("找不到 EOCD，这不是一个完整的 zip");
  }

  /** 逐个读中央目录条目，拿到每个条目的关键字段和它在文件里的位置。 */
  function listEntries(bytes) {
    const eocd = findEocd(bytes);
    const cdOffset = rd32(bytes, eocd + 16);
    const total = rd16(bytes, eocd + 10);
    const out = [];
    let p = cdOffset;
    for (let i = 0; i < total; i++) {
      if (rd32(bytes, p) !== 0x02014B50) throw new Error("中央目录条目破损 @" + p);
      const method = rd16(bytes, p + 10);
      const crc = rd32(bytes, p + 16);
      const csize = rd32(bytes, p + 20);
      const usize = rd32(bytes, p + 24);
      const nlen = rd16(bytes, p + 28);
      const xlen = rd16(bytes, p + 30);
      const clen = rd16(bytes, p + 32);
      const localOffset = rd32(bytes, p + 42);
      const flags = rd16(bytes, p + 8);
      // 名字是 UTF-8 或 latin1，这里只需要比对固定字段
      let nameBytes = bytes.subarray(p + 46, p + 46 + nlen);
      let name = "";
      for (const b of nameBytes) name += String.fromCharCode(b);
      out.push({ name, method, crc, csize, usize, localOffset, flags });
      p += 46 + nlen + xlen + clen;
    }
    return { entries: out, eocd, cdOffset };
  }

  /** local header 里数据段的起点 */
  function dataStartOf(bytes, entry) {
    const lo = entry.localOffset;
    const nlen = rd16(bytes, lo + 26);
    const xlen = rd16(bytes, lo + 28);
    return lo + 30 + nlen + xlen;
  }

  // ---------- 重建 zip（换掉一个条目，其余原样搬）----------
  function rebuildZip(bytes, replaceName, newData) {
    const { entries } = listEntries(bytes);
    const parts = [];
    const newCds = [];
    let offset = 0;

    for (const e of entries) {
      const isTarget = e.name === replaceName;
      let body, method, csize, usize, crc;

      if (isTarget) {
        body = newData;
        method = 0;                       // 存着不压，省掉一个 deflate 实现
        csize = usize = body.length;
        crc = crc32(body);
      } else {
        const ds = dataStartOf(bytes, e);
        body = bytes.subarray(ds, ds + e.csize);
        method = e.method; csize = e.csize; usize = e.usize; crc = e.crc;
      }

      // local header：30 字节固定 + 名字，不带 extra（原来的对齐 padding 不要了）
      const nameBytes = new Uint8Array(e.name.length);
      for (let i = 0; i < e.name.length; i++) nameBytes[i] = e.name.charCodeAt(i);

      const lh = new Uint8Array(30);
      const lhView = new DataView(lh.buffer);
      lhView.setUint32(0, 0x04034B50, true);
      lhView.setUint16(4, 20, true);          // version needed
      lhView.setUint16(6, 0, true);           // flags：不用 data descriptor
      lhView.setUint16(8, method, true);
      lhView.setUint16(10, 0, true);          // mod time
      lhView.setUint16(12, 0x21, true);       // mod date（1980-01-01，固定值便于复现）
      lhView.setUint32(14, crc, true);
      lhView.setUint32(18, csize, true);
      lhView.setUint32(22, usize, true);
      lhView.setUint16(26, nameBytes.length, true);
      lhView.setUint16(28, 0, true);

      const localOffset = offset;
      parts.push(lh, nameBytes, body);
      offset += 30 + nameBytes.length + body.length;

      // 中央目录条目：46 字节固定 + 名字
      const cd = new Uint8Array(46);
      const cdView = new DataView(cd.buffer);
      cdView.setUint32(0, 0x02014B50, true);
      cdView.setUint16(4, 20, true);
      cdView.setUint16(6, 20, true);
      cdView.setUint16(8, 0, true);
      cdView.setUint16(10, method, true);
      cdView.setUint16(12, 0, true);
      cdView.setUint16(14, 0x21, true);
      cdView.setUint32(16, crc, true);
      cdView.setUint32(20, csize, true);
      cdView.setUint32(24, usize, true);
      cdView.setUint16(28, nameBytes.length, true);
      cdView.setUint16(30, 0, true);
      cdView.setUint16(32, 0, true);
      cdView.setUint16(34, 0, true);
      cdView.setUint16(36, 0, true);
      cdView.setUint32(38, 0, true);
      cdView.setUint32(42, localOffset, true);
      newCds.push(cd, nameBytes);
    }

    const cdBytes = concat(newCds);
    const cdOffset = offset;

    // EOCD
    const eocd = new Uint8Array(22);
    const ev = new DataView(eocd.buffer);
    ev.setUint32(0, 0x06054B50, true);
    ev.setUint16(4, 0, true);
    ev.setUint16(6, 0, true);
    ev.setUint16(8, entries.length, true);
    ev.setUint16(10, entries.length, true);
    ev.setUint32(12, cdBytes.length, true);
    ev.setUint32(16, cdOffset, true);
    ev.setUint16(20, 0, true);

    return { bytes: concat([...parts, cdBytes, eocd]), cdOffset, eocdOffset: offset + cdBytes.length };
  }

  // ---------- 摘要 ----------
  async function sha256(data) {
    return new Uint8Array(await crypto.subtle.digest("SHA-256", data));
  }

  /** 一条链算完所有段的块，出一个总摘要。 */
  async function contentDigest(sections) {
    const hashes = [];
    for (const sec of sections) {
      for (let i = 0; i < sec.length; i += CHUNK) {
        const c = sec.subarray(i, Math.min(i + CHUNK, sec.length));
        hashes.push(await sha256(concat([new Uint8Array([0xa5]), u32(c.length), c])));
      }
    }
    const body = concat(hashes);
    return sha256(concat([new Uint8Array([0x5a]), u32(hashes.length), body]));
  }

  // ---------- v2 块 ----------
  // 每一层的长度字段都写「内容长度」，不含自己那个 4 字节前缀 —— 这是最容易错的地方。
  function signedDataContent(digest, certDer) {
    // digests: 序列(4+44)，项(4+40)，项内含 alg(4)+摘要长(4)+摘要(32)
    const digestItem = concat([u32(SIG_ALG), u32(digest.length), digest]);   // 40
    const digestsInner = concat([u32(digestItem.length), digestItem]);       // 44
    const digests = concat([u32(digestsInner.length), digestsInner]);        // 48

    // certificates: 序列(4+758)，证书项(4+754)
    const certItem = concat([u32(certDer.length), certDer]);                 // 758
    const certs = concat([u32(certItem.length), certItem]);                  // 762

    // additional attributes：空序列
    const attrs = u32(0);                                                    // 4

    // 官方实现末尾还有 4 字节 0。规范没写，但实测官方包就是这样，
    // 不补这 4 字节 apksig 会判 Malformed signer block。
    const tail = u32(0);

    return concat([digests, certs, attrs, tail]);                            // 818
  }

  function buildSigner(sdContent, sig, spki) {
    const sd = concat([u32(sdContent.length), sdContent]);                   // 822
    const sigItem = concat([u32(SIG_ALG), u32(sig.length), sig]);            // 264
    const sigsInner = concat([u32(sigItem.length), sigItem]);                // 268
    const signatures = concat([u32(sigsInner.length), sigsInner]);           // 272
    const pk = concat([u32(spki.length), spki]);                             // 298
    return concat([sd, signatures, pk]);                                     // 1392
  }

  function buildBlock(signerContent) {
    const signersInner = concat([u32(signerContent.length), signerContent]); // 1396
    const pairValue = concat([u32(signersInner.length), signersInner]);      // 1400
    const pair = concat([u64(4 + pairValue.length), u32(V2_ID), pairValue]); // 8+1404
    const blockSize = pair.length + 8 + 16;      // 自身之外的：pairs + 尾部 size + magic
    const magic = new Uint8Array([0x41, 0x50, 0x4B, 0x20, 0x53, 0x69, 0x67,
      0x20, 0x42, 0x6C, 0x6F, 0x63, 0x6B, 0x20, 0x34, 0x32]);   // "APK Sig Block 42"
    return concat([u64(blockSize), pair, u64(blockSize), magic]);
  }

  // ---------- 主流程 ----------
  /**
   * @param {Uint8Array} templateBytes 模板 APK 的原始字节
   * @param {Uint8Array} payload       要放进去的 game.html
   * @param {object} keyMaterial       {privateKey, cert, publicKey} 三个 base64
   * @returns {Promise<Uint8Array>}    签好的 APK 字节
   */
  async function signApk(templateBytes, payload, keyMaterial) {
    const b64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
    const pkcs8 = b64(keyMaterial.privateKey);
    const certDer = b64(keyMaterial.cert);
    const spki = b64(keyMaterial.publicKey);

    // 1. 换壳
    const zip = rebuildZip(templateBytes, GAME_ENTRY, payload);

    // 2. 三段。此时签名块还没插，签名块的起点就是中央目录的起点
    const blockStart = zip.cdOffset;
    const contents = zip.bytes.subarray(0, zip.cdOffset);
    const centralDir = zip.bytes.subarray(zip.cdOffset, zip.eocdOffset);
    const eocdBuf = new Uint8Array(zip.bytes.subarray(zip.eocdOffset));
    // 中央目录偏移字段改成签名块起点（虽然此刻两者相同，规则要求这么算）
    const ev = new DataView(eocdBuf.buffer);
    ev.setUint32(16, blockStart, true);

    const digest = await contentDigest([contents, centralDir, eocdBuf]);

    // 3. 签名
    const key = await crypto.subtle.importKey(
      "pkcs8", pkcs8,
      { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
      false, ["sign"]
    );
    const sd = signedDataContent(digest, certDer);
    const signature = new Uint8Array(await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, sd));

    // 4. 拼装：条目区 + 签名块 + 中央目录 + EOCD(偏移已更新)
    const block = buildBlock(buildSigner(sd, signature, spki));
    const newEocd = new Uint8Array(eocdBuf);
    new DataView(newEocd.buffer).setUint32(16, blockStart + block.length, true);

    return concat([contents, block, centralDir, newEocd]);
  }

  global.MYONLApkSign = { signApk, _internals: { rebuildZip, contentDigest, crc32, listEntries } };
})(typeof window !== "undefined" ? window : globalThis);
