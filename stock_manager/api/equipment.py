"""Kitchen equipment catalog shared by the API and HowToCook importer."""

EQUIPMENT_TERMS = {
    "oven": ("烤箱",),
    "air_fryer": ("空气炸锅",),
    "microwave": ("微波炉",),
    "pressure_cooker": ("电压力锅", "压力锅", "高压锅"),
    "rice_cooker": ("电饭煲", "电饭锅", "电锅"),
    "steamer": ("蒸锅", "蒸笼", "蒸箱", "电蒸炉"),
    "blender": ("料理机", "破壁机", "搅拌机"),
    "electric_mixer": ("电动打蛋器", "厨师机"),
    "bread_machine": ("面包机",),
    "clay_pot": ("砂锅", "瓦煲", "瓦罐"),
    "grill": ("烧烤炉",),
    "thermometer": ("温度计",),
    "kitchen_scale": ("电子秤", "厨房秤"),
}
EQUIPMENT_CODES = tuple(EQUIPMENT_TERMS)

BASIC_TOOL_TERMS = frozenset(
    "锅 炒锅 平底锅 不粘锅 煎锅 汤锅 深锅 煮锅 奶锅 铁锅 铝锅 油锅 粥锅 炖锅 "
    "普通汤锅 深汤锅 刀 菜刀 砧板 碗 盘子 盆 勺 锅铲 铲子 筷子 打蛋器 蒸架 蒸篦子 "
    "笼屉 屉布 锡纸 厨房纸 吸油纸 硅油纸 保鲜膜 一次性手套 明火 灶台 电磁炉 鏊子 "
    "烤盘 模具 擀面杖 刮刀 刮板 漏勺 笊篱 削皮刀 蒜臼 容器".split()
)
TOOL_SUFFIXES = tuple(
    "锅 刀 碗 盘 盆 勺 铲 板 炉 箱 机 器 笼 屉 垫 架 篦子 笊篱 臼 罐 容器 "
    "盖 膜 纸 布 手套 模具 杖 筷 夹 钳 秤 计 煲".split()
)
INGREDIENT_EXCEPTIONS = frozenset({"昆布", "糯米纸"})


def catalog_order(codes) -> list[str]:
    """Return known codes once each, in catalog order."""
    wanted = set(codes)
    return [code for code in EQUIPMENT_CODES if code in wanted]
