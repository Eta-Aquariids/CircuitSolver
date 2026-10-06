"""CircuitSolver 电路图界面（Tkinter）—— 只做界面，求解交给 main.py。

分工（各管各的）
----------------
* `unit.py`   ：元件线性模型 + 求解器 `solver(units, nodes, sum_nodes, sum_units)`
                ← 你维护
* `interface.py`（本文件）：画布 / 工具 / 符号 / 网表组装 / 结果显示

工具（左侧从上到下）
--------------------
* 选择：**只看不改**。点元件 → 画布上出现带数字的电流箭头，侧栏显示电流大小与方向；
        点节点 → 显示该点电位。这个模式永远不会改动电路。
* 移动：**唯一能改电路的模式**。拖元件 = 整体平移；选中后拖红色端点 = 改长度/方向；
        双击改参数，右键菜单 = 翻转 / 旋转 / 删除 / 清空，Delete 键 = 删除。
* 元件（导线 / 电阻 / 电压源 / 电流源）：在画布上按住拖动放置（任意角度，两端吸附格点）。

画布
----
网格是**无限**的：没有边、也没有滚动条，元件可以摆在任意格点（坐标为负也行）。
看别处就中键拖动平移（或 Ctrl + 左键），滚轮上下翻、Shift + 滚轮左右翻。
每 5 格画一条略深的线，方便定位。

电位标注
--------
默认**不标**所有节点电位（画布干净）；点某个节点看它自己的电位，
需要看全部就去菜单「视图 → 显示所有节点电位」。

参考点（0 V）
-------------
不用手工设地：求解时自动取排序后的第一个节点（最上一行、同行最左那个）当 0 V，
其余节点的电压都是相对它算的。元件名和电流数字的文字方向跟随元件方向。

加一种新元件（两步）
--------------------
1. 在 `unit.py` 里写好它的 Unit 子类（给出 a / b / c）；
2. 在下面 `KINDS` 里加一条 `Kind(...)`：中文名、单位、默认值、最小长度、画法、
   生成 Unit 的工厂。
   工具栏按钮、侧栏参数、网表组装、求解、绘制都会自动跟上，不用改其它代码。

直接运行：  .venv/bin/python interface.py     （或 VS Code 里点 ▶）
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import numpy as np
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, simpledialog, ttk

import unit as unit_mod     # 元件方程 + 求解器 solver()，都在 unit.py 里

# --------------------------------------------------------------------------- #
# 画布常量（「格」= 网格单位，符号尺寸也都按格算）
# --------------------------------------------------------------------------- #
GRID = 40               # 1 格 = 40 px
MARGIN = 40             # 原点离视图左上角的留白
VIEW_SPAN = 10 ** 6     # 画布对外是无限的，这是可平移半径（px）
OFFSET_PX = 24          # 并联元件沿法线错开的距离
HANDLE_R = 13           # 端点手柄命中半径
HIT_R = 12              # 元件本体命中距离
NODE_HIT_R = 8          # 节点命中半径
CTRL_MASK = 0x0004
SHIFT_MASK = 0x0001
TAG_SCH = ("sch",)      # 电路图元
TAG_GHOST = ("ghost",)  # 拖拽预览
SIGN_HALF = 5.5         # 电压源 ± 号半臂长（px）
SIGN_GAP = 13.0         # ± 号与导线错开的距离（px）
LABEL_GAP = 12.0        # 标签与电阻矩形 / 导线端点的间距（px）
SOURCE_GAP = 14.0       # 标签与圆环（电源）边缘的间距（px）


class Style:
    """配色与字体。字体在 `setup_fonts` 里按系统可用字体覆盖。"""
    normal = "#212121"
    select = "#d32f2f"
    ghost = "#8e24aa"
    label = "#37474f"
    volt = "#1565c0"
    current = "#e65100"
    node = "#90a4ae"
    grid = "#e3e3e3"
    grid_major = "#ccd3d8"
    font_label = ("DejaVu Sans", 9)
    font_small = ("DejaVu Sans", 8)
    font_mono = ("DejaVu Sans Mono", 9)


# --------------------------------------------------------------------------- #
# 中文字体
# --------------------------------------------------------------------------- #
CJK_FAMILIES = (
    "Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans SC",
    "WenQuanYi Micro Hei", "文泉驿微米黑", "WenQuanYi Zen Hei", "文泉驿正黑",
    "OPPO Sans 4.0 SC", "Microsoft YaHei", "SimHei", "PingFang SC",
)
MONO_FAMILIES = (
    "Noto Sans Mono CJK SC", "Xiaolai Mono SC", "小赖字体 等宽 SC",
    "WenQuanYi Micro Hei Mono", "文泉驿等宽微米黑",
)
NAMED_FONTS = (
    ("TkDefaultFont", 10), ("TkTextFont", 10), ("TkMenuFont", 10),
    ("TkHeadingFont", 10), ("TkIconFont", 10), ("TkCaptionFont", 10),
    ("TkSmallCaptionFont", 9), ("TkTooltipFont", 9),
)


def setup_fonts(root):
    """按系统可用字体配置 Tk 字体；返回选中的中文字体族（None = 没找到）。"""
    try:
        available = set(tkfont.families(root))
    except tk.TclError:
        available = set()
    family = next((f for f in CJK_FAMILIES if f in available), None)
    mono = next((f for f in MONO_FAMILIES if f in available), family)
    for name, size in NAMED_FONTS:
        try:
            tkfont.nametofont(name, root).configure(
                family=family or "sans-serif", size=size)
        except tk.TclError:
            pass
    try:
        tkfont.nametofont("TkFixedFont", root).configure(
            family=mono or "monospace", size=9)
    except tk.TclError:
        pass
    Style.font_label = (family or "sans-serif", 9)
    Style.font_small = (family or "sans-serif", 8)
    Style.font_mono = (mono or family or "monospace", 9)
    return family


# --------------------------------------------------------------------------- #
# 画笔：符号画法与 Tk 画布之间的唯一接口
# --------------------------------------------------------------------------- #
class Pen:
    """固定了 tags / 线型的 Tk 画笔画笔；坐标一律用「格」。"""

    def __init__(self, canvas, tags, dash=None):
        self.canvas = canvas
        self.tags = tags
        self.dash = dash

    def _kw(self):
        return {"dash": self.dash} if self.dash else {}

    def px(self, g):
        return (MARGIN + g[0] * GRID, MARGIN + g[1] * GRID)

    def line(self, p1, p2, color, width=2):
        self.canvas.create_line(p1[0], p1[1], p2[0], p2[1], fill=color,
                                width=width, tags=self.tags, **self._kw())

    def poly(self, points, fill, outline, width=2):
        self.canvas.create_polygon(*[v for p in points for v in p], fill=fill,
                                   outline=outline, width=width,
                                   tags=self.tags, **self._kw())

    def circle(self, center, r, fill, outline, width=2):
        x, y = center
        self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=fill,
                                outline=outline, width=width,
                                tags=self.tags, **self._kw())

    def rect(self, center, half, fill, outline, width=1):
        x, y = center
        self.canvas.create_rectangle(x - half, y - half, x + half, y + half,
                                     fill=fill, outline=outline, width=width,
                                     tags=self.tags)

    def text(self, at, s, color, font, anchor="center", angle=0.0):
        self.canvas.create_text(at[0], at[1], text=s, fill=color, font=font,
                                anchor=anchor, angle=angle, tags=self.tags)


# --------------------------------------------------------------------------- #
# 符号画法
# --------------------------------------------------------------------------- #
@dataclass
class Look:
    """一次绘制里的外观（由界面按「是否选中 / 是否拖拽预览」算好）。"""
    color: str = Style.normal
    label_color: str = Style.label
    width: int = 2
    offset: float = 0.0     # 并联元件沿法线的错开量（px）
    ghost: bool = False     # True = 拖拽预览（虚线、不写标签）


def _shift(p, vec, k):
    return (p[0] + vec[0] * k, p[1] + vec[1] * k)


def _frame(pen, el, offset):
    """元件在屏幕上的坐标系：两端点、单位方向 u、单位法线 n、符号中心、长度。

    法线取 (u_y, -u_x)：水平元件时指向上方。
    """
    p1, p2 = pen.px(el.n1), pen.px(el.n2)
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return None
    u = (dx / length, dy / length)
    n = (u[1], -u[0])
    center = _shift(((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2), n, offset)
    return p1, p2, u, n, center, length


def text_angle(ux, uy) -> float:
    """文字沿元件轴线的旋转角（Tk 的 `angle`），文字推进方向 = (cos A, -sin A)。

    取 n1→n2 方向；该方向朝左（x<0）时转 180°，保证文字永远不倒着写
    （竖直方向统一成向下读，即 A = -90°）。
    """
    ang = math.degrees(math.atan2(uy, ux))     # 屏幕方向角（y 轴向下）
    if ang > 90:
        ang -= 180
    elif ang < -90:
        ang += 180
    return -ang


def _label(pen, el, look, center, normal, off, u):
    """在符号外侧写「名字=参数」，文字方向跟着元件走（拖拽预览不写）。"""
    if not look.ghost:
        pen.text(_shift(center, normal, off), el.label_text(), look.label_color,
                 Style.font_label, angle=text_angle(*u))


def _sign(pen, at, plus, color):
    """± 号：始终按屏幕方向画（横竖），不随元件角度旋转。"""
    pen.line((at[0] - SIGN_HALF, at[1]), (at[0] + SIGN_HALF, at[1]), color, 2)
    if plus:
        pen.line((at[0], at[1] - SIGN_HALF), (at[0], at[1] + SIGN_HALF),
                 color, 2)


def draw_wire(pen, el, look):
    f = _frame(pen, el, look.offset)
    if f is None:
        return
    p1, p2, u, n, center, length = f
    pen.line(p1, p2, look.color, look.width)
    _label(pen, el, look, center, n, 14.0, u)


def draw_resistor(pen, el, look):
    f = _frame(pen, el, look.offset)
    if f is None:
        return
    p1, p2, u, n, center, length = f
    bh = min(GRID * 0.95, length * 0.32)          # 矩形半长
    bw = min(GRID * 0.30, length * 0.22)          # 矩形半宽
    a, b = _shift(center, u, -bh), _shift(center, u, bh)
    pen.poly([_shift(a, n, bw), _shift(b, n, bw),
              _shift(b, n, -bw), _shift(a, n, -bw)],
             fill="white", outline=look.color, width=look.width)
    pen.line(p1, a, look.color, look.width)
    pen.line(b, p2, look.color, look.width)
    _label(pen, el, look, center, n, bw + LABEL_GAP, u)


def draw_vsource(pen, el, look):
    """圆环 + 贯穿两端的直线（圆中间那条线）；− 在 n1 侧、+ 在 n2 侧。"""
    f = _frame(pen, el, look.offset)
    if f is None:
        return
    p1, p2, u, n, center, length = f
    r = min(GRID * 0.42, length * 0.30)
    pen.line(p1, p2, look.color, look.width)
    pen.circle(center, r, fill="", outline=look.color, width=look.width)
    _sign(pen, _shift(_shift(center, u, -(r + 9)), n, -SIGN_GAP), False,
          look.color)
    _sign(pen, _shift(_shift(center, u, r + 9), n, -SIGN_GAP), True,
          look.color)
    _label(pen, el, look, center, n, r + SOURCE_GAP, u)


def draw_isource(pen, el, look):
    """圆环 + 圆内垂直于导线的短杠（引线只画到圆边）+ 圆外箭头指向 n2。"""
    f = _frame(pen, el, look.offset)
    if f is None:
        return
    p1, p2, u, n, center, length = f
    r = min(GRID * 0.42, length * 0.30)
    pen.line(p1, _shift(center, u, -r), look.color, look.width)
    pen.line(_shift(center, u, r), p2, look.color, look.width)
    pen.line(_shift(center, n, -r), _shift(center, n, r), look.color, look.width)
    pen.circle(center, r, fill="", outline=look.color, width=look.width)
    tail, tip = _shift(center, u, r + 4), _shift(center, u, r + 18)
    back = _shift(tip, u, -8.0)
    bar = 5.0
    pen.line(tail, back, look.color, 2)
    pen.poly([tip, _shift(back, n, bar), _shift(back, n, -bar)],
             fill=look.color, outline=look.color, width=1)
    _label(pen, el, look, center, n, r + SOURCE_GAP, u)


# --------------------------------------------------------------------------- #
# 元件类型表：加新元件 / 改画法 / 改映射，都在这里
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Kind:
    """一种元件的全部定义。"""
    label: str                      # 中文名（工具栏 / 结果里显示）
    prefix: str                     # 自动命名前缀
    draw: Callable                  # 画符号：(pen, el, look) -> None
    make: Callable                  # 生成求解单元：(nodes, value) -> unit.Unit
    unit: str | None = None         # 参数单位；None = 没有参数（如导线）
    default: float | None = None    # 新元件默认参数
    min_span: int = 1               # 最小长度（格）
    split: bool = False             # 允许他元件端点在内部搭接（T 型分支）
    offset: bool = True             # 并联（同端点对）时错开画
    note: str = ""                  # 方向说明模板，{a}/{b} = 两端格点


KINDS: dict[str, Kind] = {
    "wire": Kind(
        label="导线", prefix="W", min_span=1, split=True, offset=False,
        draw=draw_wire,
        make=lambda pts, v: unit_mod.Unit(list(pts), 0, -1, 0),
    ),
    "resistor": Kind(
        label="电阻", prefix="R", unit="Ω", default=10.0, min_span=2,
        note="电流正方向 {a} → {b}",
        draw=draw_resistor,
        make=lambda pts, v: unit_mod.Resistor(list(pts), v),
    ),
    "vsource": Kind(
        label="电压源", prefix="U", unit="V", default=12.0, min_span=2,
        note="− 端 {a}，+ 端 {b}",
        draw=draw_vsource,
        make=lambda pts, v: unit_mod.VoltageSource(list(pts), v),
    ),
    "isource": Kind(
        label="电流源", prefix="I", unit="A", default=2.0, min_span=2,
        note="电流 {a} → {b}",
        draw=draw_isource,
        make=lambda pts, v: unit_mod.CurrentSource(list(pts), v),
    ),
}


# --------------------------------------------------------------------------- #
# 纯几何
# --------------------------------------------------------------------------- #
def fmt(value) -> str:
    """数值 -> 简短字符串。"""
    if value is None:
        return "—"
    if abs(value) < 1e-12:
        return "0"
    return f"{value:.4g}"


def point_on_interior(p, a, b) -> bool:
    """p 是否严格落在线段 a-b 的内部（不含两端）。

    用整数叉积判共线，因此对任意角度都成立。
    """
    if a == b or p == a or p == b:
        return False
    vx, vy = b[0] - a[0], b[1] - a[1]
    if vx * (p[1] - a[1]) - vy * (p[0] - a[0]) != 0:      # 不共线
        return False
    return (min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= p[1] <= max(a[1], b[1]))


def dist_point_seg(px, py, ax, ay, bx, by) -> float:
    """点到线段的最短距离。"""
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def make_placement(start, end, kind):
    """把「起点 -> 终点」规整成合法的元件两端（**任意角度**）。

    * 两端都落在格点上（终点吸附到最近的格点）；
    * 长度不足（< Kind.min_span 格，按欧氏长度）时沿原方向等比例拉长；
    * 画布是无限的，所以总能放下，直接返回 (p1, p2)。
    """
    start = (int(start[0]), int(start[1]))
    dx = int(end[0]) - start[0]
    dy = int(end[1]) - start[1]
    if dx == 0 and dy == 0:                    # 没拖动：先给一条最短的水平元件
        dx, dy = 1, 0

    g = math.gcd(abs(dx), abs(dy)) or 1        # 约成最简整数方向
    ux, uy = dx // g, dy // g
    step = math.hypot(ux, uy)
    need = KINDS[kind].min_span
    k_min = 1
    while step * k_min < need - 1e-9:          # 满足最小长度所需的最小倍数
        k_min += 1
    k = max(g, k_min)
    return (start, (start[0] + ux * k, start[1] + uy * k))


# --------------------------------------------------------------------------- #
# 元件
# --------------------------------------------------------------------------- #
class Element:
    """画布上的一个元件。

    n1 -> n2 既是几何方向，也是电学参考方向（含义由 Kind.note / make 决定）：
      电阻：i 正方向 n1 -> n2，且 u(n1) - u(n2) = R*i
      电压源：u(n2) - u(n1) = U，即 n1 侧是 −、n2 侧是 +
      电流源：i = I，电流由 n1 流向 n2
    """

    def __init__(self, kind, n1, n2, value=None, name=""):
        self.kind = kind
        self.n1 = tuple(n1)
        self.n2 = tuple(n2)
        self.value = value
        self.name = name
        self.currents = []          # 求解后：各分段电流（导线分段时可能多个）
        self.offset_index = 0.0     # 并联错开用

    @property
    def spec(self) -> Kind:
        return KINDS[self.kind]

    @property
    def has_value(self) -> bool:
        """有没有可改参数（导线没有）。"""
        return self.spec.unit is not None

    @property
    def horizontal(self) -> bool:
        return self.n1[1] == self.n2[1]

    @property
    def vertical(self) -> bool:
        return self.n1[0] == self.n2[0]

    @property
    def span(self) -> float:
        """两端距离（单位：格）。"""
        return math.hypot(self.n2[0] - self.n1[0], self.n2[1] - self.n1[1])

    def label_text(self) -> str:
        """画布上的标签：只写名字和参数（电流由选中时的箭头表示）。"""
        if not self.has_value:
            return self.name
        return f"{self.name}={fmt(self.value)}{self.spec.unit}"

    def direction_text(self) -> str:
        if self.vertical:
            text = "竖直"
        elif self.horizontal:
            text = "水平"
        else:
            ang = math.degrees(math.atan2(self.n2[1] - self.n1[1],
                                          self.n2[0] - self.n1[0]))
            text = f"斜向（{abs(ang):.1f}°）"
        note = self.spec.note
        return text + ("；" + note.format(a=self.n1, b=self.n2) if note else "")

    def flip(self):
        """翻转：交换两端（± 反号 / 箭头反向）。"""
        self.n1, self.n2 = self.n2, self.n1

    def rotate90(self):
        """以 n1 为轴旋转 90°（斜放时换到另一条对角线），长度不变。"""
        dx, dy = self.n2[0] - self.n1[0], self.n2[1] - self.n1[1]
        self.n2 = (self.n1[0] - dy, self.n1[1] + dx)


# --------------------------------------------------------------------------- #
# 网表：画布元件 -> 求解用的支路
# --------------------------------------------------------------------------- #
def split_segments(elements):
    """把画布元件展开成求解用的支路。

    `Kind.split` 的元件（导线）若被别的元件端点在内部搭接，就在搭接点断开成
    多段（T 型分支）；其它元件被搭接则只给个提示、不连接。
    返回 (segments, warnings)，segment = dict(kind, a, b, value, owner)。
    """
    segments, warnings = [], []
    for el in elements:
        taps = []
        for other in elements:
            if other is el:
                continue
            for p in (other.n1, other.n2):
                if point_on_interior(p, el.n1, el.n2) and p not in taps:
                    taps.append(p)
        if not el.spec.split:
            for p in taps:
                warnings.append(
                    f"{el.spec.label} {el.name} 的符号中段被格点 {p} 搭接，"
                    f"未构成连接（只有导线支持 T 型分支）")
            segments.append({"kind": el.kind, "a": el.n1, "b": el.n2,
                             "value": el.value, "owner": el})
            continue
        if taps:                                   # 沿导线方向投影排序
            vx, vy = el.n2[0] - el.n1[0], el.n2[1] - el.n1[1]
            key = lambda p: (p[0] - el.n1[0]) * vx + (p[1] - el.n1[1]) * vy
            chain = [el.n1] + sorted(taps, key=key) + [el.n2]
        else:
            chain = [el.n1, el.n2]
        for a, b in zip(chain, chain[1:]):
            segments.append({"kind": el.kind, "a": a, "b": b,
                             "value": el.value, "owner": el})
    return segments, warnings


def split_nodes(elements):
    """画布上的全部节点（元件端点 + T 型搭接点），顺序去重。"""
    pts = []
    for s in split_segments(elements)[0]:
        pts += [s["a"], s["b"]]
    return list(dict.fromkeys(pts))


def order_nodes(points):
    """节点排序：按 (行, 列) 排，**0 号节点就是自动选定的 0 V 参考点**。"""
    return sorted(dict.fromkeys(points), key=lambda p: (p[1], p[0]))


class SolveError(Exception):
    """电路解不出来时抛出，界面拿它给友好提示。"""


def solve_netlist(elements):
    """组装网表 → 交给 main.solver → 收拾成界面好用的结果。

    不用传参考点：`order_nodes` 排序后的第一个节点天然就是求解器的节点 0（0 V）。
    返回 dict(nodes, voltages, segments, x, warnings)；失败抛 SolveError。
    """
    segments, warnings = split_segments(elements)
    if not segments:
        raise SolveError("画布上还没有元件。")
    points = [p for s in segments for p in (s["a"], s["b"])]

    nodes = order_nodes(points)                # nodes[0] = 自动选定的 0 V 参考点
    index = {p: i for i, p in enumerate(nodes)}
    units = [KINDS[s["kind"]].make([index[s["a"]], index[s["b"]]], s["value"])
             for s in segments]

    voltages = np.zeros(len(nodes))
    try:
        unit_mod.solver(units, voltages, len(nodes), len(units))   # 求解在 unit.py
    except np.linalg.LinAlgError:
        raise SolveError("方程组奇异，无法求解。\n"
                         "常见原因：理想电压源并联冲突、纯导线回路、悬空支路，"
                         "或存在没和其它部分连起来的独立子电路。")

    for el in elements:
        el.currents = []                        # 导线分段时会有多个
    for k, s in enumerate(segments):
        s["owner"].currents.append(float(units[k].i))

    return {
        "nodes": nodes,
        "voltages": {p: float(v) for p, v in zip(nodes, voltages)},
        "segments": segments,
        "x": np.concatenate([np.array([u.i for u in units]), voltages]),
        "warnings": warnings,
    }


# --------------------------------------------------------------------------- #
# 主界面
# --------------------------------------------------------------------------- #
class CircuitApp:
    def __init__(self, root):
        self.root = root
        self.elements: list[Element] = []
        self.name_seq = {spec.prefix: 0 for spec in KINDS.values()}
        self.selected: Element | None = None
        self.selected_node = None       # 选中的节点（格点），用于显示电位
        self.solution = None            # solve_netlist 的结果
        self.show_voltages = False      # 是否把所有节点电位都标在画布上（默认不标）
        self.drag = None                # 当前拖动状态（place / move / endpoint）
        self.panning = False

        self._build_ui()
        self.set_status("在左侧选元件（导线 / 电阻 / …），在画布上按住拖动即可放置；"
                        "放好后点「⚡ 求解电路」。")

    # ------------------------------------------------------------------ UI --
    def _build_ui(self):
        self.root.title("CircuitSolver · 电路图编辑器")
        self.root.minsize(760, 520)
        try:
            ttk.Style().theme_use("clam")
        except tk.TclError:
            pass
        self._build_menu()

        outer = ttk.Frame(self.root, padding=6)
        outer.pack(fill="both", expand=True)
        self._build_left(outer)
        self._build_right(outer)
        mid = ttk.Frame(outer)
        mid.pack(side="left", fill="both", expand=True)
        self._build_canvas(mid)

        # 窗口默认取「刚好放下所有控件」的尺寸，但不超过屏幕
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth() or 1400
        sh = self.root.winfo_screenheight() or 900
        w = int(min(self.root.winfo_reqwidth() + 8, sw - 40))
        h = int(min(self.root.winfo_reqheight() + 8, sh - 80))
        self.root.geometry("%dx%d" % (max(880, w), max(600, h)))
        self.root.update_idletasks()
        self.reset_view()                # 格点 (0,0) 落在视图左上角

        self.var_status = tk.StringVar(value="")
        ttk.Label(self.root, textvariable=self.var_status, relief="sunken",
                  anchor="w", padding=(6, 3)).pack(fill="x", side="bottom")

    def _build_menu(self):
        menubar = tk.Menu(self.root)

        m_file = tk.Menu(menubar, tearoff=0)
        m_file.add_command(label="清空画布", command=self.clear_all)
        m_file.add_separator()
        m_file.add_command(label="退出", command=self.root.destroy)
        menubar.add_cascade(label="文件", menu=m_file)

        m_view = tk.Menu(menubar, tearoff=0)
        self.var_show_volt = tk.BooleanVar(value=self.show_voltages)
        m_view.add_checkbutton(label="显示所有节点电位",
                               variable=self.var_show_volt,
                               command=self.toggle_voltages)
        m_view.add_command(label="回到原点", command=self.reset_view)
        menubar.add_cascade(label="视图", menu=m_view)

        m_help = tk.Menu(menubar, tearoff=0)
        m_help.add_command(label="操作说明…", command=self.show_help)
        menubar.add_cascade(label="帮助", menu=m_help)
        self.root.configure(menu=menubar)

    def toggle_voltages(self):
        """视图菜单：是否把所有节点电位标在画布上。"""
        self.show_voltages = self.var_show_volt.get()
        self.redraw()
        self.set_status("已" + ("显示" if self.show_voltages else "隐藏")
                        + "所有节点电位（点某个节点仍会单独显示它的电位）。")

    def show_help(self):
        messagebox.showinfo(
            "操作说明",
            "选择（只看不改）：点元件 → 电流箭头 + 侧栏电流大小/方向；\n"
            "                  点节点 → 显示电位。不会改动电路。\n"
            "移动（可改电路）：拖元件 = 平移；选中后拖红色端点 = 改长度/方向；\n"
            "                  双击改参数；右键 = 翻转 / 旋转 / 删除；Delete 键删除。\n"
            "元件：按住拖动放置（任意角度，两端吸附格点）。\n"
            "0 V 参考点：求解时自动取最上一行里最靠左的节点，不用手工设地。\n"
            "视图菜单：可以打开「显示所有节点电位」或「回到原点」。\n\n"
            "平移画布：按住鼠标中键拖动（或 Ctrl + 左键拖动）。\n"
            "滚轮上下滚动，Shift + 滚轮左右滚动。\n\n"
            "提示：只是选中/查看不会让上次的解失效，不必反复求解。",
            parent=self.root)

    def _build_left(self, parent):
        left = ttk.Frame(parent)
        left.pack(side="left", fill="y", padx=(0, 6))

        box = ttk.LabelFrame(left, text="工具 / 元件")
        box.pack(fill="x")
        self.var_tool = tk.StringVar(value="select")
        tools = [("select", "选择"), ("move", "移动")]
        tools += [(key, spec.label) for key, spec in KINDS.items()]
        for key, text in tools:
            ttk.Radiobutton(box, text=text, value=key, variable=self.var_tool,
                            style="Toolbutton", width=12,
                            command=self.on_tool_change).pack(fill="x", pady=1)

        ttk.Button(left, text="⚡ 求解电路", command=self.on_solve
                   ).pack(fill="x", pady=(8, 0))

    def _build_right(self, parent):
        right = ttk.Frame(parent, width=360)
        right.pack(side="right", fill="y", padx=(6, 0))
        right.pack_propagate(False)

        sbox = ttk.LabelFrame(right, text="选中元件 / 节点")
        sbox.pack(fill="x")
        sbox.columnconfigure(0, weight=1)

        self.lbl_sel = ttk.Label(sbox, text="（未选中）", justify="left",
                                 wraplength=310)
        self.lbl_sel.grid(row=0, column=0, sticky="w", padx=6, pady=(4, 2))

        # 参数行：标签按元件类型换成对应单位（R Ω / U V / I A）
        self.row_param = ttk.Frame(sbox)
        self.row_param.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 2))
        self.lbl_param = ttk.Label(self.row_param, text="")
        self.lbl_param.pack(side="left")
        self.var_edit = tk.StringVar()
        self.entry_edit = ttk.Entry(self.row_param, textvariable=self.var_edit,
                                    width=10)
        self.entry_edit.pack(side="left", padx=4)
        self.btn_apply = ttk.Button(self.row_param, text="应用", width=6,
                                    command=self.apply_value)
        self.btn_apply.pack(side="left")

        self.lbl_cur = ttk.Label(sbox, text="", justify="left", wraplength=310,
                                 foreground=Style.volt)
        self.lbl_cur.grid(row=2, column=0, sticky="w", padx=6, pady=(0, 6))

        rbox = ttk.LabelFrame(right, text="求解结果")
        rbox.pack(fill="both", expand=True, pady=(6, 0))
        self.txt = tk.Text(rbox, width=40, height=20, wrap="word",
                           font=Style.font_mono, state="disabled",
                           background="#fafafa")
        sb = ttk.Scrollbar(rbox, command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt.pack(side="left", fill="both", expand=True)

    def _build_canvas(self, parent):
        # 网格是无限的 → 不要滚动条：中键拖动平移、滚轮滚动（见 on_wheel）
        self.canvas = tk.Canvas(parent, width=1000, height=660, bg="white",
                                highlightthickness=1,
                                highlightbackground="#b0bec5")
        self.canvas.configure(scrollregion=(-VIEW_SPAN, -VIEW_SPAN,
                                            VIEW_SPAN, VIEW_SPAN))
        self.canvas.pack(fill="both", expand=True)
        self.pen = Pen(self.canvas, TAG_SCH)
        self.pen_ghost = Pen(self.canvas, TAG_GHOST, dash=(4, 3))
        self.pen_dash = Pen(self.canvas, TAG_SCH, dash=(3, 2))

        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Button-3>", self.on_context)
        self.canvas.bind("<Double-Button-1>", self.on_double)
        # 平移：中键拖动；滚轮上下、Shift+滚轮左右（X11 的滚轮是 Button-4/5）
        self.canvas.bind("<Button-2>", self.start_pan)
        self.canvas.bind("<B2-Motion>", self.do_pan)
        self.canvas.bind("<ButtonRelease-2>", self.end_pan)
        self.canvas.bind("<Button-4>", self.on_wheel)
        self.canvas.bind("<Button-5>", self.on_wheel)
        self.canvas.bind("<Shift-Button-4>", self.on_wheel)
        self.canvas.bind("<Shift-Button-5>", self.on_wheel)
        self.root.bind("<Delete>", self.on_delete_key)
        self.root.bind("<Escape>", lambda e: self.on_escape())
        self.canvas.bind("<Configure>", lambda e: self.draw_grid())

        self.draw_grid()

    def reset_view(self):
        """把视图原点对准格点 (0,0)（画布对外表现成无限大）。"""
        self.canvas.update_idletasks()
        self.canvas.scan_mark(0, 0)
        self.canvas.scan_dragto(int(round(self.canvas.canvasx(0))),
                                int(round(self.canvas.canvasy(0))), gain=1)
        self.draw_grid()

    # ------------------------------------------------------------- 绘制 --
    def to_px(self, p):
        return (MARGIN + p[0] * GRID, MARGIN + p[1] * GRID)

    def to_grid(self, x, y):
        return (round((x - MARGIN) / GRID), round((y - MARGIN) / GRID))

    def ev_xy(self, event):
        """事件坐标 → 画布内容坐标（画布滚动/平移过时 event.x/y 是控件坐标）。"""
        return self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

    def draw_grid(self):
        """只画可视区内的网格线 → 看起来就是无限大的网格（每 5 格加深一条）。"""
        self.canvas.delete("grid")
        x0 = self.canvas.canvasx(0) - GRID
        y0 = self.canvas.canvasy(0) - GRID
        x1 = self.canvas.canvasx(self.canvas.winfo_width()) + GRID
        y1 = self.canvas.canvasy(self.canvas.winfo_height()) + GRID
        for i in range(math.floor((x0 - MARGIN) / GRID),
                       math.ceil((x1 - MARGIN) / GRID) + 1):
            x = MARGIN + i * GRID
            color = Style.grid_major if i % 5 == 0 else Style.grid
            self.canvas.create_line(x, y0, x, y1, fill=color, tags="grid")
        for j in range(math.floor((y0 - MARGIN) / GRID),
                       math.ceil((y1 - MARGIN) / GRID) + 1):
            y = MARGIN + j * GRID
            color = Style.grid_major if j % 5 == 0 else Style.grid
            self.canvas.create_line(x0, y, x1, y, fill=color, tags="grid")

    def compute_offsets(self):
        """同端点对的元件（并联支路）沿法线错开，避免符号重叠。"""
        groups = {}
        for el in self.elements:
            groups.setdefault(frozenset((el.n1, el.n2)), []).append(el)
        for els in groups.values():
            n = len(els)
            for k, el in enumerate(els):
                el.offset_index = 0.0 if n == 1 else (k - (n - 1) / 2)

    def look_of(self, el, ghost=False):
        """按「是否选中 / 是否拖拽预览」算出绘制外观。"""
        selected = (el is self.selected) and not ghost
        color = Style.ghost if ghost else (
            Style.select if selected else Style.normal)
        return Look(color=color,
                    label_color=color if selected else Style.label,
                    width=3 if selected else 2,
                    offset=(el.offset_index * OFFSET_PX
                            if el.spec.offset else 0.0),
                    ghost=ghost)

    def draw_element(self, el, ghost=False):
        pen = self.pen_ghost if ghost else self.pen
        el.spec.draw(pen, el, self.look_of(el, ghost))

    def draw_node_marks(self):
        """节点小圆点 + 连接点大圆点。"""
        endpoints, interior = {}, {}
        for el in self.elements:
            for p in (el.n1, el.n2):
                endpoints[p] = endpoints.get(p, 0) + 1
            for other in self.elements:
                if other is el:
                    continue
                for p in (other.n1, other.n2):
                    if point_on_interior(p, el.n1, el.n2):
                        interior[p] = interior.get(p, 0) + 1

        for p in set(endpoints) | set(interior):
            self.pen.circle(self.to_px(p), 2.5, Style.node, "")
        for p, cnt in endpoints.items():
            if cnt >= 3 or interior.get(p, 0) >= 1:
                self.pen.circle(self.to_px(p), 4.5, Style.normal, "")

    def draw_annotations(self):
        """每个节点的电压标注（默认关，视图菜单里可打开；选中节点仍单独显示）。"""
        if not self.solution or not self.show_voltages:
            return
        for p in self.solution["nodes"]:
            x, y = self.to_px(p)
            self.pen.text((x + 6, y - 6),
                          f"{fmt(self.solution['voltages'][p])}V", Style.volt,
                          Style.font_small, anchor="sw")

    def draw_selection(self):
        """选中态：移动模式的端点手柄、选中支路的电流箭头、选中节点的电位。"""
        el = self.selected
        if el is not None and self.editing:
            for p in (el.n1, el.n2):
                self.pen.rect(self.to_px(p), 5, Style.select, "white")
        if el is not None and self.solution is not None:
            self.draw_current_arrow(el)
        if self.selected_node is not None:
            self.draw_node_selection(self.selected_node)

    def draw_current_arrow(self, el):
        """带数字的箭头：数值 = 电流大小，箭头指向 = 实际电流方向。"""
        segs = [s for s in self.solution["segments"] if s["owner"] is el]
        for seg, cur in zip(segs, el.currents):
            if abs(cur) < 1e-12:                 # 电流为 0：不画箭头
                continue
            x1, y1 = self.to_px(seg["a"])
            x2, y2 = self.to_px(seg["b"])
            dx, dy = x2 - x1, y2 - y1
            length = math.hypot(dx, dy)
            if length < 1e-6:
                continue
            ux, uy = dx / length, dy / length
            px_, py_ = uy, -ux                   # 法线：箭头画在标签的另一侧
            if cur < 0:                          # 负电流 = 实际方向与 a→b 相反
                ux, uy = -ux, -uy
            cx = (x1 + x2) / 2 - px_ * 30.0
            cy = (y1 + y2) / 2 - py_ * 30.0
            tail = (cx - ux * 16.0, cy - uy * 16.0)
            tip = (cx + ux * 16.0, cy + uy * 16.0)
            self.pen.line(tail, tip, Style.current, 2)
            back = (tip[0] - ux * 10.0, tip[1] - uy * 10.0)
            bar = 6.0
            self.pen.poly([tip, (back[0] + px_ * bar, back[1] + py_ * bar),
                           (back[0] - px_ * bar, back[1] - py_ * bar)],
                          fill=Style.current, outline=Style.current, width=1)
            self.pen.text((cx - px_ * 14, cy - py_ * 14), f"{fmt(abs(cur))}A",
                          Style.current, Style.font_label,
                          angle=text_angle(ux, uy))

    def draw_node_selection(self, p):
        x, y = self.to_px(p)
        self.pen_dash.circle((x, y), 8, "", Style.select, 2)
        text = ("u = ？（请先求解）" if self.solution is None else
                f"u = {fmt(self.solution['voltages'].get(p))} V")
        # 靠视图右边缘时把标注放到左侧，免得被裁掉
        near_right = x > self.canvas.canvasx(self.canvas.winfo_width() - 90)
        self.pen.text((x - 11 if near_right else x + 11, y + 11), text,
                      Style.volt, Style.font_label,
                      anchor="ne" if near_right else "nw")

    def redraw(self):
        self.canvas.delete("sch")
        self.compute_offsets()
        for el in self.elements:
            self.draw_element(el)
        self.draw_node_marks()
        self.draw_annotations()
        self.draw_selection()

    def draw_ghost(self):
        self.canvas.delete("ghost")
        if not self.drag or self.drag["mode"] != "place":
            return
        kind = self.drag["kind"]
        p1, p2 = self.drag["cur"]
        tmp = Element(kind, p1, p2, KINDS[kind].default, name="…")
        self.draw_element(tmp, ghost=True)

    # --------------------------------------------------------- 工具 / 模式 --
    @property
    def tool(self) -> str:
        return self.var_tool.get()

    @property
    def editing(self) -> bool:
        """「选择」只看不改；其它工具（移动 / 元件）都能改电路。"""
        return self.tool != "select"

    def set_tool(self, key):
        self.var_tool.set(key)
        self.on_tool_change()

    def on_tool_change(self):
        self.canvas.configure(cursor={"select": "arrow",
                                      "move": "hand2"}.get(self.tool,
                                                           "crosshair"))
        if self.tool == "select":
            self.set_status("选择模式（只看不改）：点元件显示电流大小与方向，"
                            "点节点显示电位。")
        elif self.tool == "move":
            self.set_status("移动模式（可改电路）：拖元件平移，拖红色端点改长度/方向，"
                            "双击 / 右键改参数或翻转旋转删除。")
        else:
            spec = KINDS[self.tool]
            self.set_status(f"在画布上按住并拖动，放置{spec.label}"
                            f"（任意角度，两端吸附格点；长度至少 {spec.min_span} 格）。")
        self.redraw()
        self.refresh_inspector()

    def set_status(self, text):
        self.var_status.set(text)

    def on_escape(self):
        self.drag = None
        self.canvas.delete("ghost")
        self.select(None)
        self.set_tool("select")

    # --------------------------------------------------------- 命中 / 选中 --
    def hit_handle(self, x, y):
        """命中当前选中元件的端点手柄时返回 (el, 'n1'|'n2')。"""
        el = self.selected
        if el is None:
            return None
        for part in ("n1", "n2"):
            hx, hy = self.to_px(getattr(el, part))
            if math.hypot(x - hx, y - hy) <= HANDLE_R:
                return (el, part)
        return None

    def hit_element(self, x, y):
        """命中元件本体时返回该元件，否则 None。"""
        best, best_dist = None, HIT_R
        for el in self.elements:
            ax, ay = self.to_px(el.n1)
            bx, by = self.to_px(el.n2)
            d = dist_point_seg(x, y, ax, ay, bx, by)
            if d < best_dist:
                best, best_dist = el, d
        return best

    def hit_node(self, x, y):
        """命中节点（格点）时返回该点，否则 None。"""
        best, best_dist = None, NODE_HIT_R
        for p in split_nodes(self.elements):
            hx, hy = self.to_px(p)
            d = math.hypot(x - hx, y - hy)
            if d < best_dist:
                best, best_dist = p, d
        return best

    def select(self, el):
        self.selected = el
        self.selected_node = None
        self.refresh_inspector()
        self.redraw()

    def select_node(self, p):
        """选中节点并显示电位（只读操作，不影响求解结果）。"""
        self.selected = None
        self.selected_node = p
        self.refresh_inspector()
        self.redraw()
        if self.solution is None:
            self.set_status(f"节点 {p}：请先点「⚡ 求解电路」才能显示电位。")
        else:
            self.set_status(f"节点 {p}：u = "
                            f"{fmt(self.solution['voltages'].get(p))} V")

    def pick(self, x, y):
        """选择模式：只更新选中状态，任何情况下都不改电路。"""
        node = self.hit_node(x, y)
        if node is not None:
            self.select_node(node)
            return
        el = self.hit_element(x, y)
        self.select(el)
        if el is None:
            self.set_status("选择模式（只看不改）：点元件显示电流，点节点显示电位。")
        else:
            self.set_status(f"{el.name}（{el.spec.label}）{el.direction_text()}"
                            f"；要修改请切到「移动」")

    # ----------------------------------------------------- 交互：画布事件 --
    def on_press(self, event):
        if event.state & CTRL_MASK:                  # Ctrl + 左键 → 平移画布
            self.start_pan(event)
            return
        tool = self.tool
        x, y = self.ev_xy(event)
        g = self.to_grid(x, y)

        if tool == "select":                         # 只看不改
            self.drag = None
            self.pick(x, y)
            return

        if tool != "move":                           # 元件工具：拖动放置
            self.selected_node = None
            self.drag = {"mode": "place", "kind": tool, "start": g,
                         "cur": make_placement(g, g, tool)}
            self.draw_ghost()
            return

        # ---- 移动模式：改电路 ----
        handle = self.hit_handle(x, y)
        if handle is not None:
            el, part = handle
            self.select(el)
            self.drag = {"mode": "endpoint", "el": el, "part": part,
                         "dirty": False}
            self.set_status(f"拖动端点：两端吸附格点、任意角度，"
                            f"长度自动保持 ≥ {el.spec.min_span} 格")
            return
        el = self.hit_element(x, y)
        self.drag = None
        self.select(el)
        if el is not None:
            self.drag = {"mode": "move", "el": el, "g0": self.to_grid(x, y),
                         "orig": (el.n1, el.n2), "dirty": False}
            self.set_status(f"按住拖动 {el.name}（{el.spec.label}）")

    def on_motion(self, event):
        if self.panning:
            self.do_pan(event)
            return
        if not self.drag:
            return
        mode = self.drag["mode"]
        x, y = self.ev_xy(event)
        g = self.to_grid(x, y)

        if mode == "place":
            cand = make_placement(self.drag["start"], g, self.drag["kind"])
            self.drag["cur"] = cand
            self.draw_ghost()
            length = math.hypot(cand[1][0] - cand[0][0],
                                cand[1][1] - cand[0][1])
            self.set_status(f"放下 {KINDS[self.drag['kind']].label}："
                            f"{cand[0]} → {cand[1]}（{length:.1f} 格）")
            return

        el = self.drag["el"]
        changed = False
        if mode == "move":
            a, b = self.drag["orig"]
            g0 = self.drag["g0"]
            dgx, dgy = g[0] - g0[0], g[1] - g0[1]
            changed = bool(dgx or dgy)
            el.n1 = (a[0] + dgx, a[1] + dgy)
            el.n2 = (b[0] + dgx, b[1] + dgy)
        else:                                        # mode == "endpoint"
            part = self.drag["part"]
            anchor = el.n2 if part == "n1" else el.n1
            cand = make_placement(anchor, g, el.kind)
            if cand != (el.n1, el.n2):
                if part == "n1":                     # 保持 n1/n2 语义（极性不翻转）
                    el.n2, el.n1 = cand
                else:
                    el.n1, el.n2 = cand
                changed = True

        if changed:                                  # 只有真改了才让上次的解失效
            self.drag["dirty"] = True
            self.changed()
        else:
            self.redraw()

    def on_release(self, event):
        if self.panning:
            self.end_pan(event)
            return
        if not self.drag:
            return
        mode = self.drag["mode"]
        if mode == "place":
            self.finish_place()
            return

        el = self.drag.get("el")
        dirty = bool(self.drag.get("dirty"))
        self.drag = None
        if dirty:
            self.changed()
        elif el is self.selected:
            self.set_status(f"{el.name}（{el.spec.label}）{el.direction_text()}")

    def finish_place(self):
        cand = self.drag.get("cur")
        kind = self.drag["kind"]
        self.drag = None
        self.canvas.delete("ghost")
        spec = KINDS[kind]
        p1, p2 = cand
        dup = next((e for e in self.elements
                    if e.kind == kind and e.value == spec.default
                    and frozenset((e.n1, e.n2)) == frozenset((p1, p2))), None)
        if dup is not None:
            self.set_status("该位置已存在完全相同的元件，已忽略。")
            return
        el = Element(kind, p1, p2, spec.default, name=self.next_name(kind))
        self.elements.append(el)
        detail = (f"{el.name}={fmt(spec.default)}{spec.unit}" if el.has_value
                  else el.name)
        self.changed(status=f"已放置 {detail}，{spec.label}，{el.span:.1f} 格。")
        self.select(el)

    def on_double(self, event):
        if not self.editing:
            self.set_status("选择模式只看不改；要改参数请先切到「移动」。")
            return
        el = self.hit_element(*self.ev_xy(event))
        if el is None:
            return
        self.select(el)
        if el.has_value:
            self.edit_value()
        else:
            self.set_status(f"{el.spec.label}没有参数（两端等电位）。")

    def on_context(self, event):
        if not self.editing:
            self.set_status("选择模式只看不改；右键菜单在「移动」模式里。")
            return
        x, y = self.ev_xy(event)
        menu = tk.Menu(self.root, tearoff=0)
        el = self.hit_element(x, y)
        if el is not None:
            self.select(el)
            if el.has_value:
                menu.add_command(label="编辑参数…", command=self.edit_value)
            menu.add_command(label="翻转方向（交换两端 / ± 反号）",
                             command=self.flip_selected)
            if el.has_value:
                menu.add_command(label="旋转 90°", command=self.rotate_selected)
            menu.add_separator()
            menu.add_command(label="删除该元件", command=self.delete_selected)
        else:
            menu.add_command(label="清空画布", command=self.clear_all)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # --------------------------------------------------------- 画布平移 --
    def start_pan(self, event):
        """按住中键 / Ctrl+左键，拖动即可平移画布。"""
        self.panning = True
        self.canvas.scan_mark(event.x, event.y)
        self.canvas.configure(cursor="fleur")
        self.set_status("正在平移画布…（松开结束；滚轮上下、Shift+滚轮左右）")

    def do_pan(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)
        self.draw_grid()                 # 网格跟着视口走

    def end_pan(self, event=None):
        if not self.panning:
            return
        self.panning = False
        self.on_tool_change()            # 恢复光标与当前工具的提示

    def scroll_by(self, dx=0, dy=0):
        """按像素滚动视图（用 canvas 的 scan 机制，比 xview/yview 精确）。"""
        self.canvas.scan_mark(0, 0)
        self.canvas.scan_dragto(int(round(-dx)), int(round(-dy)), gain=1)
        self.draw_grid()                 # 网格跟着视口走

    def on_wheel(self, event):
        """滚轮：上下滚动；按住 Shift 横向滚动。"""
        step = GRID * 2 if event.num == 5 else -GRID * 2
        if event.state & SHIFT_MASK:
            self.scroll_by(dx=step)
        else:
            self.scroll_by(dy=step)

    # --------------------------------------------------------- 编辑操作 --
    def next_name(self, kind):
        prefix = KINDS[kind].prefix
        self.name_seq[prefix] = self.name_seq.get(prefix, 0) + 1
        return f"{prefix}{self.name_seq[prefix]}"

    def apply_value(self):
        el = self.selected
        if not self.editing or el is None or not el.has_value:
            return
        try:
            value = float(self.var_edit.get())
        except ValueError:
            messagebox.showwarning("参数无效", "请输入一个数字。", parent=self.root)
            return
        el.value = value
        self.changed(status=f"{el.name} 参数已改为 {fmt(value)}{el.spec.unit}")

    def edit_value(self):
        el = self.selected
        if el is None or not el.has_value:
            return
        value = simpledialog.askfloat(
            "编辑参数", f"{el.name}（{el.spec.label}）的数值：",
            initialvalue=el.value, parent=self.root)
        if value is None:
            return
        el.value = value
        self.changed()

    def flip_selected(self):
        if not self.editing or self.selected is None:
            return
        self.selected.flip()
        self.changed(status=f"{self.selected.name} 已翻转："
                            f"{self.selected.direction_text()}")

    def rotate_selected(self):
        el = self.selected
        if not self.editing or el is None or not el.has_value:
            return
        el.rotate90()
        self.changed(status=f"{el.name} 已旋转：{el.direction_text()}")

    def delete_selected(self):
        if not self.editing or self.selected is None:
            return
        name = self.selected.name
        self.elements.remove(self.selected)
        self.selected = None
        self.changed(status=f"已删除 {name}。")

    def on_delete_key(self, event):
        if not isinstance(self.root.focus_get(), (ttk.Entry, tk.Entry)):
            self.delete_selected()

    def clear_all(self):
        self.elements.clear()
        self.solution = None
        self.name_seq = {spec.prefix: 0 for spec in KINDS.values()}
        self.select(None)
        self.set_result_text("画布已清空。")
        self.set_status("画布已清空。")

    # --------------------------------------------------------- 求解/结果 --
    def changed(self, status=None):
        """电路被改动之后统一收口：解失效 + 侧栏/画布刷新 + 状态提示。"""
        self.prune_selection()
        if self.solution is not None:
            self.solution = None
            for el in self.elements:
                el.currents = []
            self.set_result_text("电路已修改，请重新求解。")
        self.refresh_inspector()
        self.redraw()
        if status:
            self.set_status(status)

    def prune_selection(self):
        """节点被删掉/移走后清空节点选中状态。"""
        if (self.selected_node is not None
                and self.selected_node not in set(split_nodes(self.elements))):
            self.selected_node = None

    def on_solve(self):
        try:
            res = solve_netlist(self.elements)
        except SolveError as exc:
            self.solution = None
            self.set_result_text(f"求解失败：\n{exc}")
            self.refresh_inspector()
            self.redraw()
            messagebox.showerror("无法求解", str(exc), parent=self.root)
            return
        self.solution = res
        self.prune_selection()
        self.refresh_inspector()
        self.redraw()
        self.show_results(res)
        self.set_status(f"求解完成：{len(res['segments'])} 条支路、"
                        f"{len(res['nodes'])} 个节点；"
                        f"参考点 N0 = {res['nodes'][0]}（0 V）。")

    def set_result_text(self, text):
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", text)
        self.txt.configure(state="disabled")

    def show_results(self, res):
        lines = []
        if res["warnings"]:
            lines += ["⚠ 提示"] + [f"  · {w}" for w in res["warnings"]] + [""]
        lines.append(f"=== 节点电压 (V)　N0 = {res['nodes'][0]} 为自动选定的 "
                     f"0 V 参考点 ===")
        for i, p in enumerate(res["nodes"]):
            tag = f"N{i}"
            lines.append(f"  {tag:<5} ({p[0]:>2},{p[1]:>2})  "
                         f"u = {fmt(res['voltages'][p]):>10}")
        lines.append("")
        lines.append("=== 支路电流 (A) ===")
        for el in self.elements:
            head = (f"  {el.name:<4}({el.n1[0]},{el.n1[1]})"
                    f"→({el.n2[0]},{el.n2[1]})")
            if not el.currents:
                lines.append(head + "   —")
            elif len(el.currents) == 1:
                lines.append(f"{head}  i = {fmt(el.currents[0]):>10}")
            else:                                   # 导线被 T 型分支切成多段
                lines.append(head + "  （已分段）")
                for k, c in enumerate(el.currents):
                    lines.append(f"        [{k + 1}] i = {fmt(c):>10}")
        lines.append("")
        lines.append("=== 未知量向量 x ===")
        lines.append("  " + np.array2string(res["x"], precision=4, separator=", "))
        self.set_result_text("\n".join(lines))

    # ------------------------------------------------------------ 侧栏 --
    def refresh_inspector(self):
        """侧栏只显示：可修改参数（带单位）+ 电流/电位；选择模式下是只读的。"""
        el = self.selected
        if el is None:
            self.row_param.grid_remove()
            self.var_edit.set("")
            p = self.selected_node
            if p is None:
                self.lbl_sel.configure(text="（未选中）")
                self.lbl_cur.configure(text="")
            else:
                self.lbl_sel.configure(text=f"节点 {p}")
                if self.solution is None:
                    self.lbl_cur.configure(text="电位：请先求解",
                                           foreground="#b71c1c")
                else:
                    self.lbl_cur.configure(
                        text=f"电位 u = {fmt(self.solution['voltages'].get(p))} V",
                        foreground=Style.volt)
            return

        el_spec = el.spec
        mode = "" if self.editing else "　（只读）"
        self.lbl_sel.configure(text=f"{el.name}　{el_spec.label}{mode}")
        if el.has_value:
            self.lbl_param.configure(text=f"{el_spec.prefix} ({el_spec.unit})")
            self.var_edit.set(fmt(el.value))
            self.row_param.grid()
            state = "normal" if self.editing else "disabled"
            self.entry_edit.configure(state=state)
            self.btn_apply.configure(state=state)
        else:
            self.row_param.grid_remove()         # 导线两端等电位，没有参数

        if self.solution is None:
            self.lbl_cur.configure(text="电流：请先求解", foreground="#b71c1c")
        elif not el.currents:
            self.lbl_cur.configure(text="电流：—", foreground="#546e7a")
        elif len(el.currents) == 1:
            cur = el.currents[0]
            way = f"{el.n1} → {el.n2}" if cur >= 0 else f"{el.n2} → {el.n1}"
            self.lbl_cur.configure(text=f"电流 i = {fmt(abs(cur))} A（{way}）",
                                   foreground=Style.current)
        else:
            detail = "，".join(f"{fmt(c)} A" for c in el.currents)
            self.lbl_cur.configure(text=f"电流（{len(el.currents)} 段）：{detail}",
                                   foreground=Style.current)


def main():
    root = tk.Tk()
    if setup_fonts(root) is None:
        print("[界面] 没找到中文字体族，界面上的中文可能显示为空白。\n"
              "        装一个即可，例如 fonts-wqy-zenhei / fonts-noto-cjk。")
    CircuitApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
