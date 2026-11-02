# 示例插件：@plug:shake 1.0 —— 记录一次屏幕震动（渲染层可自行消费 state["shake"]）
from engine.runtime import register_command


def shake(state, args):
    state["shake"] = {"power": float(args[0]) if args else 1.0}
    return {"type": "plug:shake", "power": state["shake"]["power"]}


register_command("shake", shake)
