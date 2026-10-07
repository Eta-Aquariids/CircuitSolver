import math
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from unit import (ControlledCurrentSource, ControlledVoltageSource,
                  CurrentSource, Resistor, VoltageSource, solver)

GRID = 30
COLS, ROWS = 20, 20              # 画布固定 20x20 格
W, H = COLS * GRID, ROWS * GRID  # 画布像素尺寸
UNITS = {"wire": None, "resistor": "Ω", "vsource": "V", "isource": "A",
         "cvsource": "V", "cisource": "A"}
MIN_LENGTH = {"wire": 1, "resistor": 3, "vsource": 2, "isource": 2,
              "cvsource": 2, "cisource": 2}
CONTROLLED = ("cvsource", "cisource")   # 受控源：画成菱形，值绑定某个测量量

Tags = str | tuple[str, ...]     # Tk 的 tag：单个字符串或一组字符串

HIT_R = GRID / 2                 # 命中半径：半格
NODE_R = 3                       # 悬浮 / 选中节点圆点半径（像素）
JUNCTION_R = 2                   # 三岔及以上交汇处黑点半径（像素）
MARK_R = 7                       # 测量示意时圈出节点的半径（像素）
C_NORMAL, C_HOVER, C_SEL = "black", "gray", "red"
# 统一字体：LaTeX 数学式那种衬线体（Times 系），中文自动回退到系统字体
FONT_FAMILY = "Times New Roman"
FONT = (FONT_FAMILY, 12, "bold")
CURSOR = {"p1": "crosshair", "p2": "crosshair", "body": "fleur", None: ""}

PALETTE = ("wire", "resistor", "vsource", "isource", "cvsource", "cisource")
UNIT_NAMES = {"wire": "导线", "resistor": "电阻",
              "vsource": "电压源", "isource": "电流源",
              "cvsource": "受控电压源", "cisource": "受控电流源"}
NAME_PREFIX = {"wire": "W", "resistor": "R", "vsource": "U", "isource": "I",
               "cvsource": "CU", "cisource": "CI"}

NEW_LEN = 3                              # 新建元件与按钮图标的长度：3 格
ICON_W, ICON_H = NEW_LEN * GRID, GRID * 1.6   # 图标尺寸，轴线在竖直中间
ICON_P1, ICON_P2 = (0, 0.8), (NEW_LEN, 0.8)     # 图标端点的格点坐标
C_GHOST = "#5599ff"                      # 放置预览色

def _shift(p, vec, k):
    return (p[0] + vec[0] * k, p[1] + vec[1] * k)


def text_angle(ux, uy) -> float:
    """文字沿元件轴线的旋转角（Tk 的 angle），保证文字不倒着写。"""
    ang = math.degrees(math.atan2(uy, ux))     # 屏幕方向角（y 轴向下）
    if ang > 90:
        ang -= 180
    elif ang < -90:
        ang += 180
    return -ang


def fmt(value) -> str:
    """数值 -> 简短字符串"""
    if value is None:
        return "—"
    if abs(value) < 1e-12:
        return "0"
    return f"{value:.4g}"


def label(name, value, unit) -> str:
    """元件文字：无单位（导线）或无数值时只写名字"""
    if unit is None or value is None:
        return name
    return f"{name}={fmt(value)}{unit}"


def part_text(kind, name, value, gain=1.0) -> str:
    """元件文字：导线只写名字；受控源写 系数*绑定测量名；其余写 名字=值单位"""
    if kind == "wire":
        return name
    if value is None or UNITS[kind] is None:
        return name
    if kind in CONTROLLED:
        if abs(gain - 1.0) < 1e-12:              # 系数 1 就不显示
            return f"{name}={value}"             # value 是测量的名字
        return f"{name}={fmt(gain)}*{value}"
    return label(name, value, UNITS[kind])


class Pen:
    """把画布图元的创建收集到 items，便于调用者获得本次绘制的图元 id"""

    def __init__(self, canvas, tags):
        self.canvas = canvas
        self.tags = tags
        self.items = []

    def line(self, p1, p2, color, width=2):
        self.items.append(self.canvas.create_line(
            p1[0], p1[1], p2[0], p2[1], fill=color,
            width=width, tags=self.tags))

    def circle(self, center, r, fill, outline, width=2):
        x, y = center
        self.items.append(self.canvas.create_oval(
            x - r, y - r, x + r, y + r, fill=fill,
            outline=outline, width=width, tags=self.tags))

    def poly(self, points, fill, outline, width=2):
        self.items.append(self.canvas.create_polygon(
            *[v for p in points for v in p], fill=fill,
            outline=outline, width=width, tags=self.tags))

    def rect(self, center, half, fill, outline, width=1):
        x, y = center
        self.items.append(self.canvas.create_rectangle(
            x - half, y - half, x + half, y + half,
            fill=fill, outline=outline, width=width, tags=self.tags))

    def text(self, at, s, color, font=FONT, anchor="center", angle=0.0):
        self.items.append(self.canvas.create_text(
            at[0], at[1], text=s, fill=color, font=font,
            anchor=anchor, angle=angle, tags=self.tags))


class CircuitCanvas(tk.Canvas):
    """绘图区：网格 + 元件绘制 + 拖动交互，坐标一律用格点

    units    : uid -> 元件数据 dict(kind, p1, p2, name, value, offset)，是唯一真相
    hover    : 悬浮的元件 uid（灰）；selected 为选中的（红）
    hover_node / sel_node : 悬浮、选中的节点格点（灰点 / 红点）
    _drag    : 拖动会话 dict(uid, part, joint, start, orig)，没在拖时为 None
    pending  : 放置模式里待放置的元件 dict(kind, name, value)，不在放置时为 None
    solution : 求解后的节点电位列表（None 表示未求解）；结果会写回元件的 i
    _node_index : 格点 -> 节点编号，供悬浮显示电位时查表
    _unit_index : uid -> 支路编号，供测量向量定位分量
    measures : 测量量列表，每项 dict(name, kind, unit/nodes, vector, value, flip)；
               kind 为 "current"（某支路电流）或 "voltage"（两节点电位差），
               flip 表示方向已反转
    pick     : 可视化选取会话 dict(kind, first)，不在选取时为 None
    """

    def __init__(self, parent, on_status=None, on_measures=None, on_name=None,
                 on_rename=None, size=(W, H), interactive=True, **kwargs):
        """建画布、初始化状态并（可选择地）绑定事件

        on_status  : 状态栏回调，缺省什么都不做
        on_measures: 测量量变化时的回调（新建 / 删除 / 重新求解）
        on_name    : 新建测量时索要名称的回调 ask(default) -> str|None，
                     返回 None 表示放弃这次新建
        on_rename  : 重命名元件的回调 rename(uid)，由界面层弹输入框
        size       : 画布像素尺寸，默认固定 COLS x ROWS 格
        interactive: False 时只当绘图面用（如按钮图标），不画网格、不响应鼠标
        """
        kwargs.setdefault("bg", "white")
        kwargs.setdefault("highlightthickness", 0)
        kwargs["width"], kwargs["height"] = size
        super().__init__(parent, **kwargs)

        self.on_status = on_status or (lambda s: None)
        self.on_measures = on_measures or (lambda: None)
        self.on_name = on_name or (lambda default: default)
        self.on_rename = on_rename or (lambda uid: None)
        self.units = {}          # uid -> 元件数据（唯一真相，画面只是它的投影）
        self._seq = 0
        self.hover = None        # 悬浮的 uid
        self.selected = None     # 选中的 uid（红）
        self.hover_node = None   # 悬浮的节点格点（灰点）
        self.sel_node = None     # 选中的节点格点（红点）
        self._drag = None        # 拖动会话
        self.pending: dict | None = None   # 放置模式：待放置的元件
        self.solution = None     # 求解后的节点电位列表；None 表示尚未求解
        self._node_index = {}    # 格点 -> 节点编号（求解时建立）
        self._unit_index = {}    # uid -> 支路编号（求解时建立）
        self.measures = []       # 测量量：dict(name, kind, unit/nodes, vector, value, flip)
        self.pick: dict | None = None   # 可视化选取会话：dict(kind, first)
        self.link_junction = True  # 拖公共节点时，把重合的端点一起带走

        if not interactive:
            return
        self.bind("<Motion>", self.on_motion)
        self.bind("<ButtonPress-1>", self.on_press)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Leave>", self.on_leave)
        self.bind("<Button-3>", self.on_right_click)
        self.bind("<Delete>", self.delete_selected)
        self.bind("<Escape>", lambda e: self.on_escape())
        self.draw_grid()

    # ---------------------------------------------------------------- 网格 --
    def to_px(self, p):
        """格点 -> 画布像素坐标"""
        return (p[0] * GRID, p[1] * GRID)

    def to_grid(self, xy):
        """画布像素坐标 -> 最近的格点（拖动吸附）"""
        return (round(xy[0] / GRID), round(xy[1] / GRID))

    def draw_grid(self):
        """浅色网格：固定 COLS x ROWS 格"""
        self.delete("grid")
        for i in range(COLS + 1):
            x = i * GRID
            self.create_line(x, 0, x, H, fill="gray", tags="grid")
        for j in range(ROWS + 1):
            y = j * GRID
            self.create_line(0, y, W, y, fill="gray", tags="grid")
        self.tag_raise("node")               # 节点圆点始终在最上层

    # ------------------------------------------------------ 元件登记与渲染 --
    def add_unit(self, kind, p1, p2, name="", value=None, offset=0.0, gain=1.0):
        """登记一个元件并画出来，返回它的 uid（后续可用 get/remove 操作）

        kind  : UNITS 里的类型名
        p1, p2: 端点格点坐标
        name  : 元件名
        value : 数值；受控源这里是绑定的测量名
        offset: 线段中点沿法向的偏移（像素）
        gain  : 受控源的系数（value 是测量名时，实际控制量为 gain * 该测量）
        """
        if kind not in UNITS:
            raise ValueError(f"未知元件类型：{kind!r}")
        self._seq += 1
        uid = f"u{self._seq}"
        self.units[uid] = dict(kind=kind, p1=tuple(p1), p2=tuple(p2),
                               name=name, value=value, offset=offset,
                               gain=gain)
        self.render(uid)
        self.refresh_nodes()                 # 新元件可能形成交汇点
        self.invalidate()
        return uid

    def get_unit(self, uid):
        """取元件数据（uid 不存在时返回 None）"""
        return self.units.get(uid)

    def measures_of(self, uid):
        """依赖某个元件的测量量下标（该支路电流、以及以它的端点为对象的电压）"""
        out = []
        for i, m in enumerate(self.measures):
            if m["kind"] == "current":
                if m["unit"] == uid:
                    out.append(i)
            else:
                gp = tuple(self.units[uid]["p1"]), tuple(self.units[uid]["p2"])
                if m["nodes"][0] in gp or m["nodes"][1] in gp:
                    out.append(i)
        return out

    def controlled_by(self, name):
        """绑定了某个测量量的受控源 uid 列表"""
        return [uid for uid, u in self.units.items()
                if u["kind"] in CONTROLLED and u["value"] == name]

    def remove(self, uid):
        """删除元件；先把依赖它的测量量删掉（测量依赖元件，反过来不成立）

        返回被连带删掉的测量量名字列表
        """
        if uid not in self.units:
            return []
        names = [self.measures[i]["name"] for i in self.measures_of(uid)]
        for i in reversed(self.measures_of(uid)):
            del self.measures[i]
        del self.units[uid]
        self.delete(uid)                     # uid 本身就是这批图元的 tag
        if self.hover == uid:
            self.hover = None
        if self.selected == uid:
            self.selected = None
        # 端点没了，对应的节点标记也要撤掉
        if self.hover_node is not None and not self.endpoints_at(self.hover_node):
            self.hover_node = None
        if self.sel_node is not None and not self.endpoints_at(self.sel_node):
            self.sel_node = None
        self.refresh_nodes()
        self.invalidate()
        return names

    def delete_selected(self, event=None):
        """删除当前选中的元件"""
        if self.selected:
            self.delete_unit(self.selected)

    def delete_unit(self, uid):
        """删除指定元件；被测量依赖时**拒绝删除**并说明原因"""
        u = self.units.get(uid)
        if u is None:
            return
        name = u["name"] or uid
        deps = [self.measures[i]["name"] for i in self.measures_of(uid)]
        if deps:
            messagebox.showinfo("无法删除",
                                f"{name} 上有测量量：{'、'.join(deps)}\n"
                                "请先在右侧删除这些测量量，再删除该元件")
            self.status(f"{name} 上有测量量，已取消删除")
            return
        self.remove(uid)
        self.status(f"已删除 {name}")

    def render(self, uid):
        """按当前状态（普通/悬浮/选中）重画一个元件：先删旧图元，再画新的"""
        u = self.units.get(uid)
        if u is None:
            return []
        self.delete(uid)
        color = (C_SEL if self.selected == uid
                 else C_HOVER if self.hover == uid else C_NORMAL)
        items = self._paint_unit(u["kind"], u["p1"], u["p2"], u["name"],
                                 u["value"], color=color, offset=u["offset"],
                                 gain=u.get("gain", 1.0),
                                 tag=(uid, "unit"))  # 既能单个操作，也能整批清空
        self.tag_raise("node")               # 新画的元件别盖住节点圆点
        return items

    def _paint_unit(self, kind, p1, p2, name, value, *, color, tag: Tags,
                    offset=0.0, gain=1.0):
        """按类型调用对应的绘制方法（导线没有值，受控源还要传系数）"""
        drawer = {"wire": self.draw_wire,
                  "resistor": self.draw_resistor,
                  "vsource": self.draw_vsource,
                  "isource": self.draw_isource,
                  "cvsource": self.draw_cvsource,
                  "cisource": self.draw_cisource}[kind]
        if kind == "wire":
            return drawer(p1, p2, name=name, color=color, offset=offset, tag=tag)
        if kind in CONTROLLED:
            return drawer(p1, p2, name=name, value=value, gain=gain,
                          color=color, offset=offset, tag=tag)
        return drawer(p1, p2, name=name, value=value,
                      color=color, offset=offset, tag=tag)

    # ------------------------------------------------------------ 命中判定 --
    def _dist_to_seg(self, p, a, b):
        """点到线段 ab 的最短距离（像素）"""
        ax, ay, bx, by = a[0], a[1], b[0], b[1]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
        return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))

    def hit_test(self, xy):
        """命中判定：先端点，后线段。返回 (uid, part) 或 None。

        part: "p1" / "p2" —— 抓到了端点；"body" —— 抓到了中部。
        多个人选时取距离最近的；后添加的元件在上层，同等距离优先命中。
        """
        # 第一优先：端点，半径 = 半格
        best, bd = None, HIT_R
        for uid in reversed(list(self.units)):          # 从上层往下层找
            u = self.units[uid]
            for part in ("p1", "p2"):
                d = math.hypot(xy[0] - self.to_px(u[part])[0],
                               xy[1] - self.to_px(u[part])[1])
                if d < bd:
                    bd, best = d, (uid, part)
        if best:
            return best
        # 第二优先：线段本体，半径 = 半格
        for uid in reversed(list(self.units)):
            u = self.units[uid]
            d = self._dist_to_seg(xy, self.to_px(u["p1"]), self.to_px(u["p2"]))
            if d < bd:
                bd, best = d, (uid, "body")
        return best

    def endpoints_at(self, gp):
        """落在格点 gp 上的所有端点 -> [(uid, part), ...]（公共节点会有多个）"""
        out = []
        for uid, u in self.units.items():
            for part in ("p1", "p2"):
                if u[part] == tuple(gp):
                    out.append((uid, part))
        return out

    def junctions(self):
        """端点数 >= 3 的格点（三岔及以上的交汇处）-> [格点, ...]"""
        count = {}
        for u in self.units.values():
            for part in ("p1", "p2"):
                count[tuple(u[part])] = count.get(tuple(u[part]), 0) + 1
        return [gp for gp, n in count.items() if n >= 3]

    # ------------------------------------------------------------ 节点标记 --
    def refresh_nodes(self):
        """重画节点圆点

        交汇点（>= 3 个端点）常显黑点；悬浮灰、选中红，同一格点红优先
        """
        self.delete("node")
        top = (self.hover_node, self.sel_node)
        for gp in self.junctions():
            if gp not in top:
                self._dot(gp, C_NORMAL, JUNCTION_R)
        if self.hover_node is not None and self.hover_node != self.sel_node:
            self._dot(self.hover_node, C_HOVER)
        if self.sel_node is not None:
            self._dot(self.sel_node, C_SEL)
        self.tag_raise("node")

    def _dot(self, gp, color, r=None):
        """在格点 gp 画一个实心圆点（tag 统一为 node）；r 缺省用 NODE_R"""
        r = NODE_R if r is None else r
        x, y = self.to_px(gp)
        self.create_oval(x - r, y - r, x + r, y + r,
                         fill=color, outline="", tags="node")

    def _hit_node(self, hit):
        """命中结果 -> 端点所在格点；命中的不是端点则为 None"""
        if hit and hit[1] in ("p1", "p2"):
            return tuple(self.units[hit[0]][hit[1]])
        return None

    def clear_selection(self):
        """取消选中（元件与节点都清）"""
        self.select(None)
        self.sel_node = None
        self.refresh_nodes()

    # ------------------------------------------------------------ 鼠标事件 --
    def status(self, text):
        """把提示文字送到状态栏"""
        self.on_status(text)

    def hover_to(self, uid):
        """设置悬浮元件并重画新旧两个；uid 为 None 表示取消悬浮"""
        if uid == self.hover:
            return
        old = self.hover
        self.hover = uid
        if old in self.units:
            self.render(old)                 # 恢复成黑色 / 红色
        if uid is not None:
            self.render(uid)                 # 变灰（选中态除外）
            u = self.units[uid]
            self.status(f"{u['name'] or uid} ({u['kind']})")

    def select(self, uid):
        """设置选中元件并重画新旧两个；uid 为 None 表示取消选中"""
        if uid == self.selected:
            return
        old = self.selected
        self.selected = uid
        if old in self.units:
            self.render(old)
        if uid is not None:
            self.render(uid)
            self.status(f"已选中 {self.units[uid]['name'] or uid}")

    def on_motion(self, event):
        """悬浮高亮 + 读数 + 光标提示（拖动中交给 on_drag，放置/选取中只跟对象）"""
        if self._drag:
            return
        if self.pending is not None:
            self.delete("probe")
            self.status("就绪")              # 放置中不留读数文字
            self._draw_ghost(self.to_grid((event.x, event.y)))
            return
        if self.pick is not None:            # 可视化选取：高亮候选对象
            self._pick_hover(self.hit_test((event.x, event.y)))
            return
        hit = self.hit_test((event.x, event.y))
        node = self._hit_node(hit)
        # 悬浮到端点时只亮节点，元件本身不变灰
        self.hover_to(None if node is not None else (hit[0] if hit else None))
        self.hover_node = node
        self.refresh_nodes()
        self._show_probe(hit)                # 已求解时显示电流 / 电位
        self.config(cursor=CURSOR[hit[1] if hit else None])

    def on_press(self, event):
        """左键按下：命中端点就选节点，命中中部才选元件

        同时开一次拖动会话 _drag，joint 是本帧要一起移动的端点集合
        （公共节点会带上所有重合的端点，避免回路被扯断）
        """
        self.focus_set()                     # 让 Delete / Esc 能收到
        if self.pending is not None:         # 放置模式：点一下就把元件放下
            self._place_at(self.to_grid((event.x, event.y)))
            return
        if self.pick is not None:            # 可视化选取：点一下算选好一步
            self._pick_step(self.hit_test((event.x, event.y)))
            return
        hit = self.hit_test((event.x, event.y))
        if hit is None:
            self.clear_selection()
            self.status("就绪")
            return
        uid, part = hit
        node = self._hit_node(hit)
        # 命中端点时只选/亮节点，元件不变红也不变灰
        self.select(None if node is not None else uid)
        self.hover_to(None if node is not None else uid)
        self.sel_node = node
        self.hover_node = node
        self.refresh_nodes()
        if node is not None:
            self.status(f"节点 {node}（{len(self.endpoints_at(node))} 个端点）")
        u = self.units[uid]
        start = self.to_grid((event.x, event.y))
        # 抓到端点时，把落在同一格点上的其它端点一起带走，避免回路被扯断
        joint = (self.endpoints_at(start)
                 if (self.link_junction and part in ("p1", "p2"))
                 else [(uid, part)])
        self._drag = {"uid": uid, "part": part, "joint": joint,
                      "start": start,
                      "orig": (u["p1"], u["p2"])}   # 按下瞬间的端点快照

    def _length(self, u):
        """元件当前长度（格）"""
        return math.hypot(u["p2"][0] - u["p1"][0], u["p2"][1] - u["p1"][1])

    def _can_move(self, joint, gp):
        """把 joint 里的端点都移到格点 gp 后，相关元件是否都还够长（>= MIN_LENGTH）

        已经短于 MIN_LENGTH 的元件允许变长（好拖回合法长度），但不允许再变短。
        """
        for uid, part in joint:
            u = self.units.get(uid)
            if u is None:
                continue
            a, b = (gp, u["p2"]) if part == "p1" else (u["p1"], gp)
            new = math.hypot(b[0] - a[0], b[1] - a[1])
            if new < MIN_LENGTH[u["kind"]] and new < self._length(u):
                return False
        return True

    def on_drag(self, event):
        """拖动：端点只动自己，中部整段平移；拖到比 MIN_LENGTH 还短时停在原位"""
        d = self._drag
        if not d or d["uid"] not in self.units:
            return
        u = self.units[d["uid"]]
        cur = self.to_grid((event.x, event.y))
        if d["part"] == "body":
            dx, dy = cur[0] - d["start"][0], cur[1] - d["start"][1]
            o1, o2 = d["orig"]
            u["p1"] = (o1[0] + dx, o1[1] + dy)       # 相对按下点算增量，不累积漂移
            u["p2"] = (o2[0] + dx, o2[1] + dy)
        else:
            if not self._can_move(d["joint"], cur):
                return                               # 太短：不予移动，保持上一帧
            for j_uid, j_part in d["joint"]:          # 端点：只动端点，公共节点同步
                if j_uid in self.units:
                    self.units[j_uid][j_part] = cur
            self.hover_node = self.sel_node = cur     # 节点标记跟着端点走
        self.render(d["uid"])
        for j_uid, _ in d["joint"]:
            if j_uid != d["uid"] and j_uid in self.units:
                self.render(j_uid)
        self.refresh_nodes()
        n = len(d["joint"])
        self.status(f"{u['name'] or d['uid']}  {u['p1']} → {u['p2']}"
                    + (f"（连带 {n-1} 个节点）" if n > 1 else ""))
        self.invalidate()                        # 几何变了，结果作废

    def on_release(self, event):
        """松开左键：结束拖动会话"""
        self._drag = None

    def on_leave(self, event):
        """鼠标移出画布：撤掉悬浮高亮、灰点与读数（拖动中不处理）"""
        if self._drag:
            return
        self.hover_to(None)
        self.hover_node = None
        self.refresh_nodes()
        self.delete("probe")
        self.status("就绪")

    # ------------------------------------------------------ 右键菜单与编辑 --
    def on_right_click(self, event):
        """右键：选取电流时切换测量正方向；平时点在元件上弹菜单"""
        pick = self.pick
        if pick is not None:
            if pick["kind"] == "current":
                pick["flip"] = not pick.get("flip", False)
                self._pick_arrow(pick.get("unit"))
                self.status("测量方向：" + ("p2 → p1（反向）" if pick["flip"]
                                          else "p1 → p2（正向）"))
            return                                   # 选取中不弹菜单
        hit = self.hit_test((event.x, event.y))
        if hit is None:
            return                                   # 空白处不弹菜单
        uid = hit[0]
        self.focus_set()
        self.sel_node = None                         # 右键是针对元件的
        self.select(uid)
        self.refresh_nodes()

        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="重命名…", command=lambda: self.on_rename(uid))
        menu.add_command(label="修改…", command=lambda: self.edit_unit(uid))
        menu.add_command(label="删除", command=lambda: self.delete_unit(uid))
        menu.tk_popup(event.x_root, event.y_root)
        menu.grab_release()

    def rename_unit(self, uid, name):
        """给元件改名；名字只影响显示，不动电路，所以不作废求解结果

        返回是否真的改了名
        """
        u = self.units.get(uid)
        if u is None:
            return False
        name = name or u["name"]
        if name == u["name"]:
            return False
        u["name"] = name
        self.render(uid)
        self.status(f"已重命名为 {name}")
        return True

    def cancel_drag(self):
        """放弃进行中的拖动会话（双击等会打断按键序列的场景用）"""
        self._drag = None

    def edit_unit(self, uid):
        """弹出对话框修改元件的名称、值（受控源则是系数与绑定测量）"""
        u = self.units.get(uid)
        if u is None:
            return
        spec = self._unit_dialog(f"修改 {u['name'] or uid}", u["kind"],
                                 name=u["name"], value=u["value"],
                                 gain=u.get("gain", 1.0))
        if spec is None:
            return
        u["name"], u["value"], u["gain"] = spec
        self.render(uid)
        self.invalidate()                    # 参数变了，结果作废
        self.status(f"已修改 {u['name'] or uid}")

    def new_unit(self, kind):
        """点左侧元件按钮：名称已按前缀自动编号，填好值后进入放置模式"""
        if kind in CONTROLLED and not self.measures:
            messagebox.showinfo("缺少测量",
                                "受控源要绑定一个测量量，请先在右侧新建测量")
            self.status("受控源需要先有测量量")
            return
        spec = self._unit_dialog(f"新建{UNIT_NAMES[kind]}", kind,
                                 name=self.next_name(kind),
                                 value=self.default_value(kind))
        if spec is not None:
            spec = (spec[0] or self.next_name(kind),) + spec[1:]  # 名字被清空则补回
            self.start_place(kind, *spec)

    def next_name(self, kind):
        """自动命名：取该类型里没用过的下一个编号，如 R1、W2、U3、I4"""
        prefix = NAME_PREFIX[kind]
        used = {u["name"] for u in self.units.values()}
        i = 1
        while f"{prefix}{i}" in used:
            i += 1
        return f"{prefix}{i}"

    def default_value(self, kind):
        """新元件的默认值：电阻/电源给 1；导线与受控源为 None（后者绑定测量）"""
        if UNITS[kind] is None or kind in CONTROLLED:
            return None
        return 1.0

    def _unit_dialog(self, title, kind, name="", value=None, gain=1.0):
        """名称 / 值输入对话框

        导线没有值那一栏；受控源填「系数 + 绑定测量」（值形如 -3*u1）；
        其余元件填数值（带单位）。返回 (name, value, gain)，取消则返回 None
        """
        unit = UNITS[kind]
        controlled = kind in CONTROLLED
        options = [m["name"] for m in self.measures]
        win = tk.Toplevel(self)
        win.title(title)
        win.transient(self.winfo_toplevel())

        body = ttk.Frame(win, padding=10)
        body.pack(fill="both", expand=True)

        name_var = tk.StringVar(value=name)
        ttk.Label(body, text="名称").grid(row=0, column=0, sticky="w", pady=2)
        name_entry = ttk.Entry(body, textvariable=name_var, width=16)
        name_entry.grid(row=0, column=1, pady=2, padx=(6, 0))

        value_var = tk.StringVar(value="" if value is None else f"{value:g}")
        gain_var = tk.StringVar(value=f"{gain:g}")
        bind_var = tk.StringVar(value=str(value) if controlled and value else "")
        if controlled:                               # 受控源：系数 + 绑定测量
            ttk.Label(body, text="系数").grid(row=1, column=0, sticky="w", pady=2)
            ttk.Entry(body, textvariable=gain_var, width=16).grid(
                row=1, column=1, pady=2, padx=(6, 0))
            ttk.Label(body, text="绑定测量").grid(row=2, column=0, sticky="w",
                                                  pady=2)
            box = ttk.Combobox(body, textvariable=bind_var, width=16,
                               state="readonly", values=options)
            box.grid(row=2, column=1, pady=2, padx=(6, 0))
            if options:
                box.current(options.index(bind_var.get())
                            if bind_var.get() in options else 0)
        elif unit is not None:                       # 除导线外都有值
            ttk.Label(body, text=f"值（{unit}）").grid(row=1, column=0,
                                                      sticky="w", pady=2)
            ttk.Entry(body, textvariable=value_var, width=16).grid(
                row=1, column=1, pady=2, padx=(6, 0))

        result = {}

        def apply():
            """校验并记下输入；输入不合法就提示并留在对话框"""
            new_name = name_var.get().strip()
            if controlled:
                if not options:
                    messagebox.showerror("缺少测量",
                                         "受控源要绑定一个测量量，请先新建测量",
                                         parent=win)
                    return
                text = gain_var.get().strip()
                try:
                    new_gain = float(text) if text else 1.0
                except ValueError:
                    messagebox.showerror("输入有误", f"系数必须是数字：{text}",
                                         parent=win)
                    return
                result["spec"] = (new_name, bind_var.get(), new_gain)
            else:
                text = value_var.get().strip()
                new_value = None
                if unit is not None and text:
                    try:
                        new_value = float(text)
                    except ValueError:
                        messagebox.showerror("输入有误", f"值必须是数字：{text}",
                                             parent=win)
                        return
                result["spec"] = (new_name, new_value, 1.0)
            win.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=2, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(buttons, text="确定", command=apply).pack(side="left", padx=4)
        ttk.Button(buttons, text="取消", command=win.destroy).pack(side="left", padx=4)

        win.bind("<Return>", lambda e: apply())
        win.bind("<Escape>", lambda e: win.destroy())
        name_entry.focus_set()
        win.grab_set()                               # 模态：先处理这个对话框
        self.wait_window(win)
        return result.get("spec")

    # ------------------------------------------------------------ 放置模式 --
    def start_place(self, kind, name="", value=None, gain=1.0):
        """进入放置模式：元件跟着鼠标预览，在画布上点一下定位"""
        self.pending = dict(kind=kind, name=name, value=value, gain=gain)
        self.delete("probe")
        self.config(cursor=CURSOR["body"])
        self.status(f"点击画布放置 {name or UNIT_NAMES[kind]}（Esc 取消）")

    def cancel_place(self):
        """取消放置，清掉预览"""
        self.pending = None
        self.delete("ghost")
        self.config(cursor="")
        self.status("已取消放置")

    def on_escape(self, event=None):
        """Esc：选取中取消选取，放置中取消放置，否则取消选中"""
        if self.pick is not None:
            self.cancel_pick()
        elif self.pending is not None:
            self.cancel_place()
        else:
            self.clear_selection()

    def _place_at(self, gp):
        """在格点 gp 登记新元件：从 gp 向右 NEW_LEN 格"""
        if self.pending is None:
            return
        kind, name, value, gain = (self.pending["kind"], self.pending["name"],
                                   self.pending["value"],
                                   self.pending.get("gain", 1.0))
        self.pending = None
        self.delete("ghost")
        self.config(cursor="")
        gp = self._clamp_place(gp)
        uid = self.add_unit(kind, gp, (gp[0] + NEW_LEN, gp[1]),
                            name=name, value=value, gain=gain)
        self.status(f"已新建 {name or uid}")

    def _draw_ghost(self, gp):
        """放置预览：用浅蓝色画在当前格点，跟随鼠标"""
        self.delete("ghost")
        if self.pending is None:
            return
        p = self.pending
        gp = self._clamp_place(gp)
        self._paint_unit(p["kind"], gp, (gp[0] + NEW_LEN, gp[1]),
                         p["name"], p["value"], gain=p.get("gain", 1.0),
                         color=C_GHOST, tag="ghost")
        self.tag_raise("node")

    def _clamp_place(self, gp):
        """放置位置限制在画布内，保证 NEW_LEN 格长的元件不越界"""
        return (min(max(gp[0], 0), COLS - NEW_LEN),
                min(max(gp[1], 0), ROWS - 1))

    # ------------------------------------------------------------ 抽象与求解 --
    def build_circuit(self):
        """把画布上的元件抽象成 unit.py 需要的结构

        返回 (units, node_volts, sum_nodes, sum_units)：
        - 每个不同的端点格点算一个节点，按首次出现的顺序编号，第一个格点即 0 号；
          不额外指定 0 电位，求解时 0 号节点就是参考节点（电压为 0）
        - 导线视为 0 欧姆电阻：两端电压相等，电流仍作为未知量求出来
        - 元件自己的 p1 -> p2 就是电流正方向，与绘制的方向一致
        """
        index, node_volts = {}, []
        for u in self.units.values():
            for part in ("p1", "p2"):
                gp = tuple(u[part])
                if gp not in index:
                    index[gp] = len(node_volts)
                    node_volts.append(0.0)       # 占位，求解后由 solver 写入
        # 编号先定下来：受控源要用测量向量，而向量按这两个表定位分量
        self._node_index = index            # 格点 -> 节点编号
        self._unit_index = {uid: k for k, uid in enumerate(self.units)}
        units = []
        for u in self.units.values():
            a, b = index[tuple(u["p1"])], index[tuple(u["p2"])]
            kind, value = u["kind"], u["value"] or 0.0
            if kind == "wire":
                units.append(Resistor((a, b), 0.0))
            elif kind == "resistor":
                units.append(Resistor((a, b), value))
            elif kind == "vsource":
                units.append(VoltageSource((a, b), value))
            elif kind == "isource":
                units.append(CurrentSource((a, b), value))
            elif kind == "cvsource":
                units.append(ControlledVoltageSource(
                    (a, b), self.control_vector(u["value"],
                                                u.get("gain", 1.0))))
            else:                                   # cisource
                units.append(ControlledCurrentSource(
                    (a, b), self.control_vector(u["value"],
                                                u.get("gain", 1.0))))
        return units, node_volts, len(node_volts), len(units)

    def find_measure(self, name):
        """按名字找测量量（受控源绑定的就是它）"""
        for m in self.measures:
            if m["name"] == name:
                return m
        return None

    def control_vector(self, name, gain=1.0):
        """受控源的控制向量：系数 × 绑定测量量的测量向量

        测量向量与 x = [各支路电流..., 各节点电位...] 同序，长度也一致，
        所以乘上系数后能直接交给 unit 里的受控源
        （未绑定或测量已失效时给零向量）。
        """
        size = len(self._unit_index) + len(self._node_index)
        m = self.find_measure(name)
        vec = self.measure_vector(m) if m is not None else None
        if vec is None:
            return [0.0] * size
        return [gain * v for v in vec]

    def solve(self):
        """把电路交给 solver 求解，结果只留在数据里（悬浮时用）"""
        if not self.units:
            self.status("画布上没有元件")
            return None
        units, node_volts, sum_nodes, sum_units = self.build_circuit()
        try:
            solver(units, node_volts, sum_nodes, sum_units)
        except ValueError as err:            # 例如矩阵奇异：方程无唯一解
            messagebox.showerror("求解失败", f"方程组无法求解：{err}")
            self.status("求解失败")
            return None
        # 支路电流写回各元件（units 与 self.units 同序），节点电位存起来
        for u, branch in zip(self.units.values(), units):
            u["i"] = branch.i
        self.solution = node_volts
        self.compute_measures()
        self.status(f"求解完成：{sum_units} 个元件、{sum_nodes} 个节点")
        return units, node_volts

    def invalidate(self):
        """电路被改动：丢弃求解结果，需要重新求解"""
        if self.solution is None:
            return
        self.solution = None
        self.delete("probe")
        for u in self.units.values():
            u.pop("i", None)
        self.compute_measures()              # 测量值一并作废
        self.status("电路已修改，请重新求解")

    # ---------------------------------------------------------------- 测量 --
    def node_order(self):
        """格点 -> 节点编号；规则与 build_circuit 一致（按首次出现的顺序）"""
        order = {}
        for u in self.units.values():
            for part in ("p1", "p2"):
                gp = tuple(u[part])
                if gp not in order:
                    order[gp] = len(order)
        return order

    def node_list(self):
        """当前节点 -> [(标签, 格点)]，标签形如 'n1 (2, 5)'"""
        return [(f"n{i} {gp}", gp) for gp, i in self.node_order().items()]

    def unit_list(self):
        """当前支路 -> [(标签, uid)]，标签形如 'R1 电阻'"""
        return [(f"{u['name'] or uid} {UNIT_NAMES[u['kind']]}", uid)
                for uid, u in self.units.items()]

    def next_measure_name(self, kind):
        """测量的默认名：I1、I2…（电流）或 U1、U2…（电压）

        取该前缀下当前没被占用的最小编号，所以删掉 I2 后再新建还会得到 I2
        """
        prefix = "I" if kind == "current" else "U"
        used = {m["name"] for m in self.measures}
        i = 1
        while f"{prefix}{i}" in used:
            i += 1
        return f"{prefix}{i}"

    def add_measure(self, name, kind, unit=None, nodes=None, flip=False):
        """新增测量量；解已知时立即算出取值"""
        self.measures.append(dict(name=name, kind=kind, unit=unit, nodes=nodes,
                                 vector=None, value=None, flip=flip))
        self.compute_measures()

    def remove_measure(self, index):
        """按下标删除测量量；先把绑定它的受控源一并删掉，再删测量本身"""
        if not (0 <= index < len(self.measures)):
            return []
        name = self.measures[index]["name"]
        removed = self.controlled_by(name)   # 受控源依赖测量，先删
        for uid in removed:
            self.remove(uid)
        del self.measures[index]
        self.compute_measures()
        return removed

    def measure_used(self, name, exclude=None):
        """名字是否已被别的测量占用（exclude 为要排除的下标，如重命名时的自身）"""
        return any(m["name"] == name and i != exclude
                   for i, m in enumerate(self.measures))

    def rename_measure(self, index, name):
        """重命名测量量；绑定了旧名字的受控源会跟着改绑

        名字与其它测量重名时拒绝改名，返回 False
        """
        if not (0 <= index < len(self.measures)):
            return False
        old = self.measures[index]["name"]
        name = name or old
        if name == old:
            return True
        if self.measure_used(name, exclude=index):
            return False
        self.measures[index]["name"] = name
        for uid in self.controlled_by(old):
            self.units[uid]["value"] = name
            self.render(uid)
        self.compute_measures()
        return True

    def reverse_measure(self, index):
        """反转该测量的方向：电流翻转正方向，电压交换两端

        目前方向在新建时用右键选定（见 start_pick），此方法供外部调用。
        """
        if 0 <= index < len(self.measures):
            m = self.measures[index]
            m["flip"] = not m.get("flip", False)
            self.compute_measures()

    def measure_vector(self, m):
        """把测量量写成向量：分量顺序与 x = [各支路电流..., 各节点电位...] 一致

        电流 i_k    -> 第 k 个分量取 1
        电压 u_a-u_b -> 节点 a、b 对应的分量取 +1 / -1
        flip 为真时整体取负，即反向
        """
        vec = [0.0] * (len(self._unit_index) + len(self._node_index))
        if m["kind"] == "current":
            k = self._unit_index.get(m["unit"])
            if k is None:
                return None
            vec[k] = 1.0
        else:
            base = len(self._unit_index)
            ia = self._node_index.get(m["nodes"][0])
            ib = self._node_index.get(m["nodes"][1])
            if ia is None or ib is None:
                return None
            vec[base + ia] += 1.0
            vec[base + ib] -= 1.0
        if m.get("flip"):
            vec = [-v for v in vec]
        return vec

    def solution_vector(self):
        """求解结果组成的 x；未求解时返回 None"""
        if self.solution is None:
            return None
        return [u.get("i", 0.0) for u in self.units.values()] + list(self.solution)

    def compute_measures(self):
        """重建各测量量的向量，并与 x 点乘取值；未求解时清空"""
        x = self.solution_vector()
        for m in self.measures:
            vec = self.measure_vector(m) if x is not None else None
            m["vector"] = vec
            m["value"] = (sum(v * xi for v, xi in zip(vec, x))
                          if vec is not None and x is not None else None)
        self.on_measures()

    def measure_texts(self):
        """测量量列表的显示文字，如 'i1 = 0.5A'；未求解时只写名字，不带单位"""
        out = []
        for m in self.measures:
            name = f"-{m['name']}" if m.get("flip") else m["name"]
            if m["value"] is None:           # 未求解：不显示数值与单位
                out.append(name)
            else:
                unit = "A" if m["kind"] == "current" else "V"
                out.append(f"{name} = {fmt(m['value'])}{unit}")
        return out

    def show_measure(self, m):
        """在画布上示意一个测量量：电流画方向箭头，电压圈出两个节点

        传 None 表示清掉示意。示意统一用 tag "mark"，与悬浮读数 "probe" 分开，
        两者可以同时存在（例如一边看列表、一边悬浮看数值）
        """
        self.delete("mark")
        if m is None:
            return
        if m["kind"] == "current":
            self._mark_current(m)
        else:
            self._mark_voltage(m)
        self.tag_raise("mark")

    def _mark_current(self, m):
        """电流示意：沿支路的箭头（指向测量正方向）+ 名称"""
        u = self.units.get(m["unit"])
        frame = self._frame(u["p1"], u["p2"], u["offset"]) if u else None
        if frame is None:
            self.status("该测量对应的元件已不存在")
            return
        _, _, axis, normal, center, _ = frame
        sign = -1.0 if m.get("flip") else 1.0
        tip = _shift(center, axis, sign * 14.0)
        tail = _shift(center, axis, -sign * 14.0)
        self.create_line(tail[0], tail[1], tip[0], tip[1], fill=C_SEL,
                         arrow="last", arrowshape=(9, 11, 4), width=2,
                         tags="mark")
        at = _shift(center, normal, -16.0)
        self.create_text(at[0], at[1], text=m["name"], fill=C_SEL,
                         font=FONT, tags="mark")

    def _mark_voltage(self, m):
        """电压示意：两个节点各画一个红圈，并标出 + / −（对象 − 参考）"""
        a, b = m["nodes"]
        for gp, sign in ((a, "+"), (b, "−")):
            if gp not in self.node_order():
                self.status("该测量对应的节点已不存在")
                return
            x, y = self.to_px(gp)
            self.create_oval(x - MARK_R, y - MARK_R, x + MARK_R, y + MARK_R,
                             outline=C_SEL, width=2, tags="mark")
            self.create_text(x, y - MARK_R - 2, text=sign, anchor="s",
                             fill=C_SEL, font=FONT, tags="mark")
        p, q = self.to_px(a), self.to_px(b)
        self.create_line(p[0], p[1], q[0], q[1], fill=C_SEL, dash=(4, 4),
                         tags="mark")
        mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
        self.create_text(mid[0], mid[1] - 10, text=m["name"], fill=C_SEL,
                         font=FONT, tags="mark")

    # ------------------------------------------------------------ 可视化选取 --
    def start_pick(self, kind):
        """进入可视化选取：电流点某条支路，电压先后点对象、参考两个节点

        电流选取时用箭头标出测量正方向，右键可在确定前切换方向
        """
        self.pick = dict(kind=kind, first=None, flip=False, unit=None)
        self.sel_node = None
        self.hover_to(None)
        self.hover_node = None
        self.refresh_nodes()
        self.delete("probe")
        self.config(cursor="crosshair")
        self.status("请点击要测量的支路：左键确定、右键切换方向（Esc 取消）"
                    if kind == "current" else "请点击对象节点（Esc 取消）")

    def cancel_pick(self):
        """取消可视化选取"""
        self._end_pick("已取消选取")

    def _end_pick(self, text):
        """结束选取会话：清高亮、箭头与光标提示"""
        self.pick = None
        self.hover_to(None)
        self.hover_node = None
        self.sel_node = None
        self.refresh_nodes()
        self.delete("probe")
        self.config(cursor="")
        self.status(text)

    def _pick_step(self, hit):
        """选取过程中的一次点击（左键）"""
        pick = self.pick
        if pick is None:
            return
        if hit is None:
            self.status("请点在元件或节点上（Esc 取消）")
            return
        if pick["kind"] == "current":
            uid = hit[0]
            name = self.on_name(self.next_measure_name("current"))
            if name is None:                 # 名称框里取消了，放弃这次新建
                self._end_pick("已放弃新建测量")
                return
            self.add_measure(name, "current", unit=uid, flip=pick["flip"])
            self._end_pick(f"已新建测量 {name}"
                          + ("（反向）" if pick["flip"] else ""))
            return
        gp = self._hit_node(hit)
        if gp is None:
            self.status("电压测量要点在节点（元件端点）上")
            return
        first = pick["first"]
        order = self.node_order()
        if first is None:                    # 第一步：对象节点
            pick["first"] = gp
            self.sel_node = gp               # 红点标出已选节点
            self.refresh_nodes()
            self.status(f"已选对象节点 n{order.get(gp, '?')} {gp}，"
                        "请点击参考节点（Esc 取消）")
            return
        name = self.on_name(self.next_measure_name("voltage"))
        if name is None:
            self._end_pick("已放弃新建测量")
            return
        self.add_measure(name, "voltage", nodes=(first, gp))
        self._end_pick(f"已新建测量 {name}")

    def _pick_hover(self, hit):
        """选取过程中跟随鼠标高亮候选：电流亮支路并画方向箭头，电压亮节点"""
        pick = self.pick
        if pick is None:
            return
        if pick["kind"] == "current":
            self.hover_node = None
            uid = hit[0] if hit else None
            self.hover_to(uid)
            pick["unit"] = uid
            self._pick_arrow(uid)
            hint = "请点击要测量的支路：左键确定、右键切换方向（Esc 取消）"
        else:
            self.hover_to(None)
            self.hover_node = self._hit_node(hit)
            hint = ("请点击对象节点（Esc 取消）" if pick["first"] is None
                    else "请点击参考节点（Esc 取消）")
        self.refresh_nodes()
        self.config(cursor="crosshair")
        self.status(hint)

    def _pick_arrow(self, uid):
        """电流选取的箭头预览：箭头指向测量正方向，'+' 在正极一端"""
        self.delete("probe")
        u = self.units.get(uid)
        frame = self._frame(u["p1"], u["p2"], u["offset"]) if u else None
        if frame is None:
            return
        _, _, axis, normal, center, _ = frame
        flip = bool(self.pick and self.pick.get("flip"))
        sign = -1.0 if flip else 1.0          # 不反向时正方向就是 p1 -> p2
        tip = _shift(center, axis, sign * 14.0)
        tail = _shift(center, axis, -sign * 14.0)
        self.create_line(tail[0], tail[1], tip[0], tip[1], fill=C_GHOST,
                         arrow="last", arrowshape=(9, 11, 4), width=2,
                         tags="probe")
        at = _shift(center, normal, -16.0)
        self.create_text(at[0], at[1], text="+", fill=C_GHOST, font=FONT,
                         tags="probe")

    # ------------------------------------------------------------ 悬浮读数 --
    def _show_probe(self, hit):
        """悬浮读数：元件显示电流方向与大小，节点显示电位"""
        self.delete("probe")
        if hit is None or self.solution is None:
            self.status("就绪")              # 没有读数时底栏回到就绪
            return
        uid, part = hit
        u = self.units.get(uid)
        if u is None:
            return
        if part == "body":
            self._probe_current(u)
        else:
            self._probe_voltage(tuple(u[part]))

    def _probe_current(self, u):
        """在元件上画箭头（指向电流方向）与电流大小，同时写到状态栏"""
        cur = u.get("i")
        frame = self._frame(u["p1"], u["p2"], u["offset"])
        if cur is None or frame is None:
            return
        _, _, axis, normal, center, _ = frame
        sign = 1.0 if cur >= 0 else -1.0      # 正方向为 p1 -> p2
        tip, tail = (_shift(center, axis, sign * 14.0),
                     _shift(center, axis, -sign * 14.0))
        self.create_line(tail[0], tail[1], tip[0], tip[1], fill=C_SEL,
                         arrow="last", arrowshape=(9, 11, 4), width=2,
                         tags="probe")
        at = _shift(center, normal, -16.0)
        text = f"{fmt(cur)}A"
        self.create_text(at[0], at[1], text=text, fill=C_SEL,
                         font=FONT, tags="probe")
        self.status(f"{u['name'] or '元件'} {text}")

    def _probe_voltage(self, gp):
        """在节点旁显示该点电位，同时写到状态栏"""
        idx = self._node_index.get(gp)
        volts = self.solution
        if idx is None or volts is None:
            return
        x, y = self.to_px(gp)
        text = f"{fmt(volts[idx])}V"
        self.create_text(x, y - 14, text=text, fill=C_SEL,
                         font=FONT, tags="probe")
        self.status(f"节点 {gp} {text}")

    # ------------------------------------------------------------ 元件绘制 --
    def draw_wire(self, p1, p2, name="", *, color="black", width=2,
                  offset=0.0, tag: Tags = "unit"):
        """画导线：p1→p2 直线 + 名称；长度 < MIN_LENGTH["wire"] 时不绘制"""
        frame = self._frame(p1, p2, offset)
        if frame is None:
            return []
        p1, p2, u, n, center, length = frame
        if length < MIN_LENGTH["wire"]:
            return []
        pen = Pen(self, tag)
        pen.line(p1, p2, color, width)
        pen.text(_shift(center, n, 14.0), name, color, angle=text_angle(*u))
        return pen.items

    def draw_resistor(self, p1, p2, name="", value=None, *, color="black",
                      width=2, offset=0.0, tag: Tags = "unit"):
        """画电阻：矩形（半长 1 格、半宽 0.3 格）+ 两端引线 + 文字 name=valueΩ"""
        frame = self._frame(p1, p2, offset)
        if frame is None:
            return []
        p1, p2, u, n, center, length = frame
        if length < MIN_LENGTH["resistor"]:
            return []
        pen = Pen(self, tag)
        text = part_text("resistor", name, value)
        bh = GRID * 0.80       # 矩形半长
        bw = GRID * 0.30       # 矩形半宽
        a, b = _shift(center, u, -bh), _shift(center, u, bh)
        pen.poly([_shift(a, n, bw), _shift(b, n, bw),
                  _shift(b, n, -bw), _shift(a, n, -bw)],
                 fill="white", outline=color, width=width)
        pen.line(p1, a, color, width)
        pen.line(b, p2, color, width)
        pen.text(_shift(center, n, bw + 12.0), text, color,
                 angle=text_angle(*u))
        return pen.items

    def draw_vsource(self, p1, p2, name="", value=None, *, color="black",
                     width=2, offset=0.0, tag: Tags = "unit"):
        """画电压源：圆（r = 0.5 格）+ ± 号 + 文字 name=valueV

        ± 号分列圆心沿 u 的 ±(r+9) 处，并沿 n 偏移 -13 让开导线
        """
        frame = self._frame(p1, p2, offset)
        if frame is None:
            return []
        p1, p2, u, n, center, length = frame
        if length < MIN_LENGTH["vsource"]:
            return []
        pen = Pen(self, tag)
        text = part_text("vsource", name, value)
        r = GRID * 0.5
        pen.line(p1, p2, color, width)
        pen.circle(center, r, fill="", outline=color, width=width)
        half, gap = 5.5, 13.0                   # ± 号半臂长、与导线的错开量
        for along, plus in ((-(r + 9), False), (r + 9, True)):
            at = _shift(_shift(center, u, along), n, -gap)
            pen.line(_shift(at, u, -half), _shift(at, u, half), color, 2)
            if plus:
                pen.line(_shift(at, n, -half), _shift(at, n, half), color, 2)
        pen.text(_shift(center, n, r + 14.0), text, color,
                 angle=text_angle(*u))
        return pen.items

    def draw_isource(self, p1, p2, name="", value=None, *, color="black",
                     width=2, offset=0.0, tag: Tags = "unit"):
        """画电流源：圆（r = 0.5 格）+ 横线 + 指向 p2 的箭头 + 文字 name=valueA"""
        frame = self._frame(p1, p2, offset)
        if frame is None:
            return []
        p1, p2, u, n, center, length = frame
        if length < MIN_LENGTH["isource"]:
            return []
        pen = Pen(self, tag)
        text = part_text("isource", name, value)
        r = GRID * 0.5
        pen.line(p1, _shift(center, u, -r), color, width)
        pen.line(_shift(center, u, r), p2, color, width)
        pen.line(_shift(center, n, -r), _shift(center, n, r), color, width)
        pen.circle(center, r, fill="", outline=color, width=width)
        tail, tip = _shift(center, u, r + 4), _shift(center, u, r + 18)
        back = _shift(tip, u, -8.0)
        bar = 5.0
        pen.line(tail, back, color, 2)
        pen.poly([tip, _shift(back, n, bar), _shift(back, n, -bar)],
                 fill=color, outline=color, width=1)
        pen.text(_shift(center, n, r + 14.0), text, color,
                 angle=text_angle(*u))
        return pen.items

    def draw_cvsource(self, p1, p2, name="", value=None, *, gain=1.0,
                      color="black", width=2, offset=0.0, tag: Tags = "unit"):
        """画受控电压源：菱形（r = 0.5 格）+ ± 号 + 文字 name=系数*绑定测量名

        与电压源一致，只是把圆换成菱形；± 号位置也相同
        """
        frame = self._frame(p1, p2, offset)
        if frame is None:
            return []
        p1, p2, u, n, center, length = frame
        if length < MIN_LENGTH["cvsource"]:
            return []
        pen = Pen(self, tag)
        text = part_text("cvsource", name, value, gain)
        r = GRID * 0.5
        pen.line(p1, p2, color, width)
        pen.poly([_shift(center, u, r), _shift(center, n, r),
                  _shift(center, u, -r), _shift(center, n, -r)],
                 fill="", outline=color, width=width)
        half, gap = 5.5, 13.0
        for along, plus in ((-(r + 9), False), (r + 9, True)):
            at = _shift(_shift(center, u, along), n, -gap)
            pen.line(_shift(at, u, -half), _shift(at, u, half), color, 2)
            if plus:
                pen.line(_shift(at, n, -half), _shift(at, n, half), color, 2)
        pen.text(_shift(center, n, r + 14.0), text, color,
                 angle=text_angle(*u))
        return pen.items

    def draw_cisource(self, p1, p2, name="", value=None, *, gain=1.0,
                      color="black", width=2, offset=0.0, tag: Tags = "unit"):
        """画受控电流源：菱形 + 横线 + 箭头 + 文字 name=系数*绑定测量名

        与电流源一致，只是把圆换成菱形
        """
        frame = self._frame(p1, p2, offset)
        if frame is None:
            return []
        p1, p2, u, n, center, length = frame
        if length < MIN_LENGTH["cisource"]:
            return []
        pen = Pen(self, tag)
        text = part_text("cisource", name, value, gain)
        r = GRID * 0.5
        pen.line(p1, _shift(center, u, -r), color, width)
        pen.line(_shift(center, u, r), p2, color, width)
        pen.poly([_shift(center, u, r), _shift(center, n, r),
                  _shift(center, u, -r), _shift(center, n, -r)],
                 fill="", outline=color, width=width)
        pen.line(_shift(center, n, -r), _shift(center, n, r), color, width)
        tail, tip = _shift(center, u, r + 4), _shift(center, u, r + 18)
        back = _shift(tip, u, -8.0)
        bar = 5.0
        pen.line(tail, back, color, 2)
        pen.poly([tip, _shift(back, n, bar), _shift(back, n, -bar)],
                 fill=color, outline=color, width=1)
        pen.text(_shift(center, n, r + 14.0), text, color,
                 angle=text_angle(*u))
        return pen.items

    def _frame(self, p1, p2, offset=0.0):
        """端点格点坐标 -> 绘制用的局部坐标系

        p1, p2 : 端点像素坐标
        u      : 轴向单位向量，方向 p1 -> p2
        n      : 法向单位向量
        center : 线段中点沿 n 平移 offset 后的点
        length : 长度（格）；两端点重合时返回 None
        """
        a, b = self.to_px(p1), self.to_px(p2)
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy) / GRID
        if length < 1e-9:
            return None
        u = (dx / GRID / length, dy / GRID / length)
        n = (u[1], -u[0])
        center = _shift(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), n, offset)
        return a, b, u, n, center, length


class UnitIcon(CircuitCanvas):
    """新建按钮的图标：不画网格、不响应鼠标，只画一个 NEW_LEN 格长的元件

    按下时底色变灰、元件整体变白并下沉 1 像素，作为点击反馈
    """

    def __init__(self, parent, kind, **kwargs):
        kwargs.setdefault("highlightthickness", 1)
        kwargs.setdefault("highlightbackground", "gray")
        super().__init__(parent, size=(ICON_W, ICON_H), interactive=False,
                         **kwargs)
        self.kind = kind
        self.pressed = False
        self._paint()
        self.bind("<Enter>", lambda e: self.config(cursor="hand2"))
        self.bind("<Leave>", lambda e: self.config(cursor=""))

    def _paint(self):
        """按当前按下状态重画图标：按下时用白色（线、外框、填充都是白）"""
        self.delete("icon")
        self._paint_unit(self.kind, ICON_P1, ICON_P2, "", None,
                         color="white" if self.pressed else C_NORMAL,
                         tag="icon")


    def set_pressed(self, pressed):
        """按下 / 松开：换底色并重画图标"""
        if pressed == self.pressed:
            return
        self.pressed = pressed
        self.config(bg="lightgray" if pressed else "white")
        self._paint()


class Interface(tk.Tk):
    """主窗口：左侧新建按钮 + 画布 + 底部状态栏"""

    def __init__(self):
        super().__init__()
        self.title("CircuitSolver")

        self.status = tk.StringVar(value="就绪")
        ttk.Label(self, textvariable=self.status, relief="sunken",
                  anchor="w").pack(side="bottom", fill="x")

        row = ttk.Frame(self)
        row.pack(side="top", anchor="w", padx=10, pady=10)
        left = ttk.Frame(row)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        ttk.Button(left, text="求解", command=self.solve).pack(
            side="bottom", fill="x", pady=(10, 0))
        new_units = ttk.LabelFrame(left, text="电路元件", padding=10)
        new_units.pack(side="top", fill="both", expand=True)
        self._build_palette(new_units)
        self._build_canvas(row)
        self._build_measures(row)

    def _build_canvas(self, parent):
        """建绘图区：左边一列新建按钮，右边是画布"""
        frame = ttk.LabelFrame(parent, text="电路搭建", padding=10)
        # sticky="ns"：与左栏一起撑到行高（取两者自然高度的较大值），两栏等高
        frame.grid(row=0, column=1, sticky="ns")

        self.canvas = CircuitCanvas(frame, on_status=self.status.set,
                                    on_measures=self._refresh_measures,
                                    on_name=self.ask_measure_name,
                                    on_rename=self.rename_unit)
        self.canvas.pack(side="top", anchor="w")              # 画布尺寸固定，靠左上
        self.canvas.bind("<Double-Button-1>", self._on_canvas_double)

    def rename_unit(self, uid):
        """重命名元件：右键菜单与画布双击都走这里"""
        u = self.canvas.get_unit(uid)
        if u is None:
            return
        old = u["name"] or uid
        name = self._name_dialog(f"重命名 {old}", old, ok_text="重命名")
        if name is None:
            return
        if not self.canvas.rename_unit(uid, name):
            self.status.set("名称未改变")

    def _on_canvas_double(self, event):
        """画布上双击元件：重命名"""
        hit = self.canvas.hit_test((event.x, event.y))
        if hit is None:
            return
        self.canvas.cancel_drag()            # 双击会打断按键序列，先收掉拖动会话
        self.rename_unit(hit[0])

    def ask_measure_name(self, default):
        """测量名称输入框：预填默认名，回车即用默认名；取消返回 None

        与已有测量重名时提示并重新输入，避免两个测量共用一个名字
        """
        while True:
            name = self._name_dialog("测量名称", default)
            if name is None:
                return None
            if not self.canvas.measure_used(name):
                return name
            messagebox.showerror("名称重复", f"已有名为 {name} 的测量量")
            default = name                  # 保留输入，便于改一个字再试

    def _name_dialog(self, title, default, ok_text="确定"):
        """通用名称输入框：预填并全选，回车确认；取消返回 None"""
        win = tk.Toplevel(self)
        win.title(title)
        win.transient(self)

        body = ttk.Frame(win, padding=10)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="名称").grid(row=0, column=0, sticky="w")

        name_var = tk.StringVar(value=default)
        entry = ttk.Entry(body, textvariable=name_var, width=20)
        entry.grid(row=0, column=1, padx=(6, 0))
        entry.selection_range(0, "end")      # 全选，方便直接改名
        entry.focus_set()

        result = {}

        def apply():
            result["name"] = name_var.get().strip() or default
            win.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=1, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(buttons, text=ok_text, command=apply).pack(side="left", padx=4)
        ttk.Button(buttons, text="取消", command=win.destroy).pack(side="left", padx=4)
        win.bind("<Return>", lambda e: apply())
        win.bind("<Escape>", lambda e: win.destroy())

        win.grab_set()
        self.wait_window(win)
        return result.get("name")            # 取消时返回 None

    def _build_measures(self, parent):
        """最右的「测量」栏：测量量列表 + 新建 / 删除"""
        box = ttk.LabelFrame(parent, text="测量", padding=10)
        box.grid(row=0, column=2, sticky="ns", padx=(10, 0))

        self.measure_list = tk.Listbox(box, width=20, height=12,
                                       font=FONT, exportselection=False)
        self.measure_list.pack(fill="both", expand=True)
        self.measure_list.bind("<<ListboxSelect>>",
                               lambda e: self._show_measure_mark())
        self.measure_list.bind("<Double-Button-1>",
                               lambda e: self.rename_measure())

        buttons = ttk.Frame(box)
        buttons.pack(fill="x", pady=(6, 0))
        ttk.Button(buttons, text="新建", command=self.new_measure).pack(
            side="left", fill="x", expand=True, padx=(0, 3))
        ttk.Button(buttons, text="删除", command=self.delete_measure).pack(
            side="left", fill="x", expand=True, padx=(3, 0))

    def _refresh_measures(self):
        """把 canvas 里的测量量刷到列表上（求解 / 增删 / 改动时都会调用）"""
        if not hasattr(self, "measure_list"):
            return
        self.measure_list.delete(0, "end")
        for text in self.canvas.measure_texts():
            self.measure_list.insert("end", text)
        self.canvas.show_measure(None)       # 列表重建后选中态已失效，清掉示意

    def _show_measure_mark(self):
        """列表选中项的电流 / 电压示意图"""
        selected = self.measure_list.curselection()
        if not selected:
            self.canvas.show_measure(None)
            return
        index = selected[0]
        measures = self.canvas.measures
        if 0 <= index < len(measures):
            self.canvas.show_measure(measures[index])

    def delete_measure(self):
        """删除列表里选中的测量量；绑定它的受控源会一并删除"""
        selected = self.measure_list.curselection()
        if not selected:
            self.status.set("请先在测量列表里选中一项")
            return
        removed = self.canvas.remove_measure(selected[0])
        if removed:
            names = ", ".join(self.canvas.units.get(uid, {}).get("name") or uid
                              for uid in removed)
            self.status.set(f"已删除测量量，并删除绑定它的受控源：{names}")
        else:
            self.status.set("已删除测量量")

    def rename_measure(self):
        """双击列表项：重命名测量量；重名会被拒绝，绑定它的受控源会自动改绑"""
        selected = self.measure_list.curselection()
        if not selected:
            return
        index = selected[0]
        m = self.canvas.measures[index]
        name = self._name_dialog("重命名测量", m["name"], ok_text="重命名")
        if name is None or name == m["name"]:
            return
        if self.canvas.measure_used(name, exclude=index):
            messagebox.showerror("名称重复", f"已有名为 {name} 的测量量")
            self.status.set(f"名称 {name} 已被占用，未改名")
            return
        bound = self.canvas.controlled_by(m["name"])
        self.canvas.rename_measure(index, name)
        text = f"已重命名为 {name}"
        if bound:
            text += f"，{len(bound)} 个受控源已改绑"
        self.status.set(text)

    def new_measure(self):
        """新建测量：先选类型，再到画布上点选支路 / 节点"""
        win = tk.Toplevel(self)
        win.title("新建测量")
        win.transient(self)

        body = ttk.Frame(win, padding=10)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="测量类型").pack(anchor="w")

        def start(kind):
            win.destroy()                          # 先关掉模态窗，再进画布选取
            self.canvas.start_pick(kind)

        row = ttk.Frame(body)
        row.pack(pady=(6, 4))
        ttk.Button(row, text="电流（点支路）",
                   command=lambda: start("current")).pack(side="left", padx=4)
        ttk.Button(row, text="电压（点两个节点）",
                   command=lambda: start("voltage")).pack(side="left", padx=4)
        ttk.Label(body, text="电流：左键确定，右键切换正方向").pack(anchor="w")
        ttk.Label(body, text="Esc 可取消选取").pack(anchor="w")

        win.bind("<Escape>", lambda e: win.destroy())
        win.grab_set()
        self.wait_window(win)

    def _build_palette(self, bar):
        """左侧「新建元件」按钮，自上而下排列；按钮不带文字，图标就是元件本身"""
        for kind in PALETTE:
            icon = UnitIcon(bar, kind)
            icon.pack(side="top", pady=2)
            icon.bind("<ButtonPress-1>", lambda e, i=icon: i.set_pressed(True))
            icon.bind("<ButtonRelease-1>",
                      lambda e, i=icon, k=kind: self._on_icon_release(i, k))

    def _on_icon_release(self, icon, kind):
        """松开按钮：恢复外观；在按钮上松手才算点中，移出去松手视为取消"""
        icon.set_pressed(False)
        if 0 <= icon.winfo_pointerx() - icon.winfo_rootx() < ICON_W \
                and 0 <= icon.winfo_pointery() - icon.winfo_rooty() < ICON_H:
            self.canvas.new_unit(kind)

    def solve(self):
        """求解按钮：由画布抽象电路并调用 solver"""
        self.canvas.solve()


if __name__ == "__main__":
    app = Interface()
    c = app.canvas
    app.mainloop()
