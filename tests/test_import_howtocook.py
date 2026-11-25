"""scripts/import_howtocook.py on a small fake HowToCook tree (#46).

No network and no real .env: the module is loaded with load_dotenv blocked,
and every run uses a throwaway SQLite file.
"""

import importlib.util
import json
from hashlib import sha256
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from stock_manager.api.models import Base, Recipe

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "import_howtocook.py"

RECIPE_MD = """# {title}的做法

简单好做。

## 必备原料和工具

- 鸡蛋 2个
- 盐
- 番茄（1个）
- 鲤鱼（约 1.5 斤，让店家处理内脏）
- 盐

## 计算

- 鸡蛋 2 个

## 操作步骤

1. 打散鸡蛋
2. 下锅

![{title}-预览图-1](./1.jpeg)
"""

FILES = {
    "dishes/breakfast/茶叶蛋.md": "茶叶蛋",
    "dishes/meat_dish/口水鸡/口水鸡.md": "口水鸡",  # nested one level deeper
    "dishes/dessert/焦糖布丁/焦糖布丁.md": "焦糖布丁",
    "dishes/soup/番茄蛋汤.md": "番茄蛋汤",
}


NON_RECIPES = [
    "README.md",
    "tips/learn/学习炒菜.md",
    ".github/pull_request_template.md",
    "dishes/template/示例菜/示例菜.md",
]


def _counts(**overrides):
    base = {"imported": 0, "existing": 0, "fixed": 0, "ingredients_synced": 0, "steps_synced": 0, "titles_synced": 0,
            "errors": 0, "non_recipe": 0, "pruned": 0}
    base.update(overrides)
    return base


@pytest.fixture(scope="module")
def importer():
    import dotenv

    original = dotenv.load_dotenv

    def blocked(*args, **kwargs):
        raise AssertionError("importing the script must not load .env")

    dotenv.load_dotenv = blocked
    try:
        spec = importlib.util.spec_from_file_location("import_howtocook_under_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        dotenv.load_dotenv = original
    return module


@pytest.fixture()
def repo(tmp_path):
    # A parent folder literally named "dishes" must not confuse the category.
    root = tmp_path / "dishes" / "HowToCook"
    for rel, title in FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(RECIPE_MD.format(title=title), encoding="utf-8")
    # Not recipes: must never be imported.
    for rel in NON_RECIPES:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(RECIPE_MD.format(title="不是菜"), encoding="utf-8")
    return root


@pytest.fixture()
def db(tmp_path):
    url = f"sqlite:///{tmp_path / 'import.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield url, session
    session.close()
    engine.dispose()


def _ingredient_rows(session):
    from stock_manager.api.models import RecipeIngredient

    session.expire_all()
    return sorted(
        (i.recipe_id, i.sort_order, i.ingredient_name, i.quantity, i.unit, i.is_seasoning)
        for i in session.query(RecipeIngredient).all()
    )


def _categories(session):
    session.expire_all()
    return {r.source_path: r.category for r in session.query(Recipe).all()}


class TestHowtocookCategory:
    @pytest.mark.parametrize("path,expected", [
        ("dishes/breakfast/茶叶蛋.md", "breakfast"),
        ("dishes/meat_dish/口水鸡/口水鸡.md", "meat_dish"),
        ("dishes/x.md", ""),
        ("tips/learn/a.md", ""),
    ])
    def test_first_directory_under_dishes(self, importer, path, expected):
        assert importer.howtocook_category(path) == expected

    @pytest.mark.parametrize("path,expected", [
        ("dishes/breakfast/茶叶蛋.md", True),
        ("dishes/meat_dish/口水鸡/口水鸡.md", True),
        ("dishes/template/示例菜/示例菜.md", False),
        ("dishes/README.md", False),
        ("tips/learn/a.md", False),
        (".github/pull_request_template.md", False),
        ("README.md", False),
    ])
    def test_is_recipe_path(self, importer, path, expected):
        assert importer.is_recipe_path(path) is expected


class TestParseIngredients:
    def test_names_quantities_notes_and_duplicates(self, importer):
        text = "\n".join([
            "- 剑骨鱼或鲤鱼（约 1.5 斤，让店家处理内脏，但**不要刮鱼鳞**）",
            "- 漓泉啤酒（一瓶，约 330ml，桂林本地啤酒）",
            "- 黄油(one small box)",
            "- 花椒",
            "- 花椒",
            "- 鲜面条（要求最细的，请参考[焖面](./焖面.md)）",
            "- （色拉油 或 菜籽油） 1000 ml",
            "- （适量）",
        ])
        rows = [(r["ingredient_name"], r["quantity"], r["unit"], r["sort_order"])
                for r in importer._parse_ingredients(text)]
        assert rows == [
            ("剑骨鱼", None, None, 0),
            ("鲤鱼", "1.5", "斤", 1),
            ("漓泉啤酒", "330", "ml", 2),
            ("黄油", None, None, 3),
            ("花椒", None, None, 4),
            ("鲜面条", None, None, 5),  # nested brackets from a markdown link
            ("色拉油 或 菜籽油", "1000", "ml", 6),  # only a note: its text is the name
            ("适量", None, None, 7),
        ]


class TestParseSteps:
    def test_only_real_steps_are_kept(self, importer):
        text = "\n".join([
            "1. 西红柿切丁",
            "2. 2 个鸡蛋打散",          # a number right after the marker stays
            "3) 加入 [水淀粉](./水淀粉.md) 搅拌",
            "* 撒上<b>葱花</b>",
            "> 小贴士：火不要太大",
            "### 装盘",                 # sub-heading: not a step
            "| 步骤 | 时间 |",            # table row: not a step
            "![预览图](./1.jpeg)",      # image only: not a step
            "盛出前![图](./2.jpg)尝一下咸淡",
            "<img src='./3.jpg' />",
        ])
        assert [(s["step_number"], s["instruction"]) for s in importer._parse_steps(text)] == [
            (1, "西红柿切丁"),
            (2, "2 个鸡蛋打散"),
            (3, "加入 水淀粉 搅拌"),
            (4, "撒上葱花；小贴士：火不要太大"),
            (5, "【装盘】盛出前尝一下咸淡"),
        ]

    @pytest.mark.parametrize("line,expected", [
        (">- 11.硅油纸：防粘", "硅油纸：防粘"),   # list item inside a quote
        ("1. 3.5 克盐", "3.5 克盐"),           # "3." followed by a digit is not a marker
        ("- 1.5 kg 牛肉", "1.5 kg 牛肉"),
        ("10、 出锅", "出锅"),
        ("---", ""), ("* * *", ""), ("___", ""),  # horizontal rules
        ("- -", ""), ("-", ""), ("- ：", ""), ("（）", ""),  # nothing but punctuation
    ])
    def test_clean_line_edge_cases(self, importer, line, expected):
        assert importer._clean_line(line) == expected

    def test_ingredient_starting_with_a_number_keeps_its_quantity(self, importer):
        rows = importer._parse_ingredients("* 5 g 盐\n* 2个鸡蛋\n![图](./a.png)")
        assert [(r["ingredient_name"], r["quantity"], r["unit"]) for r in rows] == [
            ("盐", "5", "g"), ("鸡蛋", "2", "个"),
        ]


class TestImport:
    def test_fresh_import_stores_dishes_directory(self, importer, repo, db):
        url, session = db
        result = importer.import_howtocook(str(repo), url)

        assert result == _counts(imported=4)
        assert _categories(session) == {
            "dishes/breakfast/茶叶蛋.md": "breakfast",
            "dishes/meat_dish/口水鸡/口水鸡.md": "meat_dish",
            "dishes/dessert/焦糖布丁/焦糖布丁.md": "dessert",
            "dishes/soup/番茄蛋汤.md": "soup",
        }
        recipe = session.query(Recipe).filter_by(source_path="dishes/meat_dish/口水鸡/口水鸡.md").one()
        assert recipe.title == "口水鸡"
        # Number and unit stored separately (#47); bracketed notes dropped from
        # names and the duplicate 盐 skipped (#49).
        assert [(i.ingredient_name, i.quantity, i.unit, i.sort_order) for i in recipe.ingredients] == [
            ("鸡蛋", "2", "个", 0), ("盐", None, None, 1), ("番茄", "1", "个", 2),
            ("鲤鱼", "1.5", "斤", 3),
        ]
        assert len(recipe.steps) == 2

    @pytest.mark.parametrize(("title", "expected"), [
        (" 拔丝土豆 的做法 ", "拔丝土豆"),
        ("的做法", "的做法"),
        ("土豆的做法合集", "土豆的做法合集"),
    ])
    def test_title_suffix(self, importer, tmp_path, title, expected):
        path = tmp_path / "recipe.md"
        path.write_text(f"# {title}\n", encoding="utf-8")
        assert importer.parse_recipe_md(str(path))["title"] == expected

    def test_rerun_updates_title_and_keeps_fork_and_user_titles(self, importer, repo, db, capsys):
        url, session = db
        importer.import_howtocook(str(repo), url)
        rel = "dishes/meat_dish/口水鸡/口水鸡.md"
        recipe = session.query(Recipe).filter_by(source_path=rel).one()
        recipe.title = "口水鸡的做法"
        fork = Recipe(title="口水鸡的做法", source_type="user", base_recipe_id=recipe.id)
        user = Recipe(title="我的菜的做法", source_type="user", source_path=rel)
        session.add_all([fork, user])
        session.commit()

        result = importer.import_howtocook(str(repo), url)

        session.expire_all()
        assert result == _counts(existing=4, titles_synced=1)
        assert recipe.title == "口水鸡"
        assert fork.title == "口水鸡的做法"
        assert user.title == "我的菜的做法"
        assert f"↻ {rel}: title '口水鸡的做法' → '口水鸡'" in capsys.readouterr().out

    def test_rerun_fixes_old_categories_and_adds_nothing(self, importer, repo, db):
        url, session = db
        importer.import_howtocook(str(repo), url)
        # Simulate rows written by the old importer (dish folder as category).
        for recipe in session.query(Recipe).all():
            if recipe.source_path.count("/") == 3:
                recipe.category = recipe.source_path.split("/")[2]
        session.commit()
        assert _categories(session)["dishes/meat_dish/口水鸡/口水鸡.md"] == "口水鸡"

        result = importer.import_howtocook(str(repo), url)

        assert result == _counts(existing=4, fixed=2)
        assert _categories(session)["dishes/meat_dish/口水鸡/口水鸡.md"] == "meat_dish"
        assert _categories(session)["dishes/dessert/焦糖布丁/焦糖布丁.md"] == "dessert"
        assert session.query(Recipe).count() == 4

    def test_rerun_reparses_old_ingredient_rows(self, importer, repo, db):
        from stock_manager.api.models import RecipeIngredient

        url, session = db
        importer.import_howtocook(str(repo), url)
        fresh = _ingredient_rows(session)

        # Rows as older importers wrote them, in two of the four recipes.
        first, second = session.query(Recipe).order_by(Recipe.id).limit(2).all()
        for ing in first.ingredients:
            if ing.ingredient_name == "鸡蛋":
                ing.quantity = "2个"                       # unit inside quantity (#47)
            if ing.ingredient_name == "鲤鱼":
                ing.ingredient_name = "鲤鱼（约 ，让店家处理内脏）"  # leftover note
        session.add(RecipeIngredient(recipe_id=second.id, ingredient_name="盐", sort_order=4))  # duplicate
        session.commit()
        assert _ingredient_rows(session) != fresh

        result = importer.import_howtocook(str(repo), url)

        assert result == _counts(existing=4, ingredients_synced=2)
        assert _ingredient_rows(session) == fresh

    def test_rerun_reparses_old_step_rows(self, importer, repo, db):
        from stock_manager.api.models import RecipeStep

        url, session = db
        importer.import_howtocook(str(repo), url)
        session.expire_all()
        fresh = sorted((s.recipe_id, s.step_number, s.instruction) for s in session.query(RecipeStep))
        assert not any("![" in step[2] for step in fresh)

        # Older imports kept the preview image as an extra step.
        recipe = session.query(Recipe).order_by(Recipe.id).first()
        session.add(RecipeStep(recipe_id=recipe.id, step_number=3, instruction="![预览图](./1.jpeg)"))
        session.commit()

        result = importer.import_howtocook(str(repo), url)

        assert result == _counts(existing=4, steps_synced=1)
        session.expire_all()
        assert sorted((s.recipe_id, s.step_number, s.instruction) for s in session.query(RecipeStep)) == fresh

    def test_third_run_changes_nothing(self, importer, repo, db):
        url, _ = db
        importer.import_howtocook(str(repo), url)
        importer.import_howtocook(str(repo), url)
        assert importer.import_howtocook(str(repo), url) == _counts(existing=4)


def _add_old_non_recipe_rows(session):
    """Rows the old importer created for tips/, .github/ and the template."""
    from stock_manager.api.models import RecipeFavorite, RecipeStep

    ids = []
    for rel in NON_RECIPES[1:]:
        recipe = Recipe(title=rel, source_type="howtocook", source_path=rel)
        session.add(recipe)
        session.flush()
        session.add(RecipeStep(recipe_id=recipe.id, step_number=1, instruction="x"))
        ids.append(recipe.id)
    session.add(RecipeFavorite(recipe_id=ids[0]))
    session.commit()
    return ids


class TestNonRecipeFiles:
    def test_only_dishes_are_imported(self, importer, repo, db):
        url, session = db
        importer.import_howtocook(str(repo), url)
        paths = {r.source_path for r in session.query(Recipe).all()}
        assert paths == set(FILES)

    def test_old_non_recipe_rows_are_listed_not_deleted(self, importer, repo, db):
        url, session = db
        _add_old_non_recipe_rows(session)

        result = importer.import_howtocook(str(repo), url)

        assert result == _counts(imported=4, non_recipe=3)
        assert session.query(Recipe).count() == 7

    def test_prune_deletes_them_with_favorites(self, importer, repo, db):
        from stock_manager.api.models import RecipeFavorite, RecipeStep

        url, session = db
        _add_old_non_recipe_rows(session)

        result = importer.import_howtocook(str(repo), url, prune_non_recipes=True)

        assert result == _counts(imported=4, non_recipe=3, pruned=3)
        session.expire_all()
        assert {r.source_path for r in session.query(Recipe).all()} == set(FILES)
        assert session.query(RecipeFavorite).count() == 0
        assert session.query(RecipeStep).count() == 4 * 2  # only the real recipes' steps

    def test_missing_dishes_dir_exits(self, importer, tmp_path, db):
        url, _ = db
        with pytest.raises(SystemExit):
            importer.import_howtocook(str(tmp_path), url)


def test_import_requires_an_explicit_database_url(importer, repo, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        importer.import_howtocook(str(repo))


def test_import_photos_and_align_on_rerun(importer, tmp_path, db, monkeypatch, capsys):
    from stock_manager.api import media
    from stock_manager.api.models import RecipePhoto
    from tests.test_recipe_photos import image_bytes

    url, session = db
    root = tmp_path / "HowToCook"
    folder = root / "dishes" / "soup"
    folder.mkdir(parents=True)
    path = folder / "soup.md"
    text = """# 汤的做法

![封面](first.png)
![越界](../../../outside.png)

## 操作步骤

* 加水。
![步骤](step.png)
![预览图](preview.png)
![缺失](missing.png)
![远程](https://example.invalid/image.png)

* 加盐。
![成品](finished.png)
"""
    path.write_text(text, encoding="utf-8")
    for name, color in [("first", "red"), ("step", "blue"), ("preview", "green"), ("finished", "pink")]:
        (folder / f"{name}.png").write_bytes(image_bytes(color=color))
    (tmp_path / "outside.png").write_bytes(image_bytes())
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "media"))

    no_photos = importer.import_howtocook(str(root), url)
    assert "photos" not in no_photos
    assert session.query(RecipePhoto).count() == 0

    result = importer.import_howtocook(str(root), url, with_photos=True)
    assert result["photos"] == dict(added=4, updated=0, removed=0, missing=2, remote_skipped=1)
    output = capsys.readouterr().out
    assert "photos: added 4, updated 0, removed 0, missing 2, remote_skipped 1" in output
    assert f"Images are missing. Run: git -C {root} sparse-checkout disable" in output

    def photos():
        session.expire_all()
        return {Path(p.source_path).name: p for p in session.query(RecipePhoto)}

    rows = photos()
    assert {name: (p.step_number, p.position, p.caption) for name, p in rows.items()} == {
        "first.png": (None, 0, "封面"), "step.png": (1, 0, "步骤"),
        "preview.png": (None, 1, "预览图"), "finished.png": (None, 2, "成品"),
    }
    rows["first.png"].is_cover = True
    rows["step.png"].hidden = True
    first_id = rows["first.png"].id
    old_hash = rows["first.png"].sha256
    removed_hash = rows["finished.png"].sha256
    session.commit()
    (folder / "first.png").write_bytes(image_bytes(color="black"))
    path.write_text(text.replace("![成品](finished.png)", "").replace("![封面]", "![新封面]"),
                    encoding="utf-8")

    rerun = importer.import_howtocook(str(root), url, with_photos=True)
    assert rerun["photos"] == dict(added=0, updated=1, removed=1, missing=2, remote_skipped=1)
    after = photos()
    assert set(after) == {"first.png", "step.png", "preview.png"}
    assert (after["first.png"].id, after["first.png"].is_cover, after["first.png"].caption) == (
        first_id, True, "新封面",
    )
    assert after["step.png"].hidden
    assert after["first.png"].sha256 != old_hash
    for sha in (old_hash, removed_hash):
        assert not media.image_path(sha).exists()
        assert not media.image_path(sha, "thumb").exists()


def test_with_photos_requires_media_configuration(importer, repo, db):
    url, _ = db
    with pytest.raises(RuntimeError, match="MEDIA_DIR is required"):
        importer.import_howtocook(str(repo), url, with_photos=True)


def test_prune_non_recipe_deletes_photo_files(importer, repo, db, tmp_path, monkeypatch):
    from dataclasses import asdict

    from stock_manager.api import media
    from stock_manager.api.models import RecipePhoto
    from tests.test_recipe_photos import image_bytes

    url, session = db
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "media"))
    media.reload_config()
    stored = media.store_image(image_bytes())
    recipe = Recipe(title="Tip", source_type="howtocook", source_path="tips/rice.md")
    session.add(recipe)
    session.flush()
    session.add(RecipePhoto(recipe_id=recipe.id, position=0, origin="howtocook", **asdict(stored)))
    session.commit()

    assert importer.import_howtocook(str(repo), url, prune_non_recipes=True)["pruned"] == 1
    assert session.query(RecipePhoto).count() == 0
    assert not media.image_path(stored.sha256).exists()
    assert not media.image_path(stored.sha256, "thumb").exists()


def test_image_and_link_targets_may_contain_parentheses(importer):
    markdown = (
        "# 血浆鸭的做法\n\n![血浆鸭(特辣)](./血浆鸭(特辣).jpg)\n\n"
        "## 操作\n\n- 下锅翻炒 ![翻炒](./步骤(1).jpg)\n- 见[说明(详细)](./说明(详细).md)出锅\n"
    )
    assert importer._photo_steps(markdown, [1, 2]) == [
        ("血浆鸭(特辣)", "./血浆鸭(特辣).jpg", None),
        ("翻炒", "./步骤(1).jpg", 1),
    ]
    assert importer._clean_line("- 下锅翻炒 ![翻炒](./步骤(1).jpg)") == "下锅翻炒"
    assert importer._clean_line("- 见[说明(详细)](./说明(详细).md)出锅") == "见说明(详细)出锅"
    # Two references on one line stay separate.
    assert [ref for _, ref, _ in importer._photo_steps("![a](a(1).jpg) 和 ![b](b.jpg)", [])] == [
        "a(1).jpg", "b.jpg",
    ]


@pytest.mark.parametrize("line,names,groups", [
    ('烤箱', [], [['oven']]),
    ('烤箱 大小不限', [], [['oven']]),
    ('烤箱 *（**不要使用不带控温的烤箱**）*', [], [['oven']]),
    ('④烤箱：烘烤食材。烤箱分为小型的经济型烤箱和大型的专业烤箱。', [], [['oven']]),
    ('需要烤箱 1 个（有上下火功能的最佳，也可以没有）', [], [['oven']]),
    ('1 个空气炸锅（喜欢脆的切忌小牌子）', [], [['air_fryer']]),
    ('可选：空气炸锅烤架（用烤架油比较少）', [], []),
    ('空气炸锅或者油锅', [], []),
    ('高压锅（推荐）或普通汤锅', [], []),
    ('炖煮锅，高压锅（可选，但极度推荐！）', [], []),
    ('电压力锅（可以极大简化烹饪过程和时间）', [], [['pressure_cooker']]),
    ('瓦罐或者高压锅', [], [['pressure_cooker', 'clay_pot']]),
    ('砂锅（相比于炒锅更适合炖汤）', [], [['clay_pot']]),
    ('砂锅（没有的话，用铁锅也行）', [], []),
    ('砂锅或深汤锅', [], []),
    ('蒸锅（电饭煲即可）', [], [['rice_cooker', 'steamer']]),
    ('蒸锅或电蒸炉', [], [['steamer']]),
    ('烤箱（电饭锅可替代，但大多情况下由于锅胆材质问题易失败）', [], [['oven', 'rice_cooker']]),
    ('烤箱或明火', [], []),
    ('平底锅 或 微波炉', [], []),
    ('分可控火候微波炉或不可控火候微波炉', [], [['microwave']]),
    ('能放进微波炉的容器', [], [['microwave']]),
    ('2 个大碗（推荐微波炉专用碗）', [], []),
    ('保鲜膜或微波炉专用盖', [], []),
    ('烧烤炉', [], [['grill']]),
    ('电磁炉/灶台', [], []),
    ('32 厘米以上的炒锅一个(锅太小难炒', [], []),
    ('100°C 沸水锅（直径≥ 15cm）', [], []),
    ('一次性手套', [], []),
    ('厨房纸', [], []),
    ('塑料盘或塑料盆（腌鱼用）', [], []),
    ('鏊子 或 平底不粘锅（直径不小于 28 cm）', [], []),
    ('注：如果有可能，请尽量把刀磨的锋利一些。', [], []),
    ('蒸鱼豉油', ['蒸鱼豉油'], []),
    ('板栗', ['板栗'], []),
    ('火锅底料（随意）', ['火锅底料'], []),
    ('肥牛（火锅肥牛即可，也可选用原切肥牛片）', ['肥牛'], []),
    ('火锅牛肉卷', ['火锅牛肉卷'], []),
    ('清水（蒸锅用）2000ml', ['清水'], []),
    ('盐（出锅调味）', ['盐'], []),
    ('白醋（建议使用 9 度的醋）', ['白醋'], []),
    ('北京二锅头酒（可选）', ['北京二锅头酒'], []),
    ('泡好的粉丝（放碗底）', ['泡好的粉丝'], []),
    ('面团（封锅口用）', ['面团'], []),
    ('昆布', ['昆布'], []),
    ('调味料：火锅底料、花生酱、全脂牛奶', ['火锅底料', '花生酱', '全脂牛奶'], []),
    ('油 + 锅 + 菜刀 + 铲子', ['油'], []),
    ('烤箱（普通的炒锅也行）', [], []),
    ("清水 720g + 600g（720 克用于蒸饭，后 500g 用于发酵）", ["清水"], []),
    ("混合馅（猪肉 + 虾滑，猪肉 + 螺肉等自由组合）", ["混合馅"], []),
    ("生抽 + 老抽 + 蚝油", ["生抽", "老抽", "蚝油"], []),
    (
        "普通无涂层炒锅可以使用木质、不锈钢或耐高温硬质硅胶炒勺；"
        "不粘锅建议使用耐高温硬质硅胶炒勺，避免损伤涂层。",
        [], [],
    ),
    ("炒糖色过程火不要太大！！！电磁炉温度不够，火候过了发苦，不够发甜", [], []),
    ("冰糖：炒出来的`糖色`色泽最为鲜艳，红亮，必须水油炒，不加水融化会很慢", ["冰糖"], []),
    ("> 荞麦面：pdd买食尚烩荞麦面，一包400g，价格4.9元，可以做4份", ["荞麦面"], []),
    ("> 花椒油：pdd五丰黎红花椒油400ml,32元两瓶，可以做80份", ["花椒油"], []),
    ("谷朊粉：这是从小麦中提取出来的蛋白质，在吸水后会形成网格状结构。", ["谷朊粉"], []),
    ("火锅底料：某宝小龙坎传统清油火锅底料味道最佳，29.8元一包，可以做20份", ["火锅底料"], []),
    ("④烤箱：烘烤食材……", [], [["oven"]]),
    (
        "香叶， 花椒，八角，干辣椒，丁香，甘草，干辣椒，小米辣（可选），姜，蒜",
        ["香叶", "花椒", "八角", "干辣椒", "丁香", "甘草", "小米辣", "姜", "蒜"], [],
    ),
    ("可选（洒在顶部）", [], []),
    ("可选（巧克力味）", [], []),
    ("**原料**", [], []),
    ("**工具**", [], []),
    ("工具", [], []),
    (
        "调味料：火锅底料、花生酱、全脂牛奶、生抽、辣椒油、醋、花椒油",
        ["火锅底料", "花生酱", "全脂牛奶", "生抽", "辣椒油", "醋", "花椒油"], [],
    ),
    ("主料：`五花肉`", ["五花肉"], []),
    ("调味料: 酱油，盐", ["酱油", "盐"], []),
    ("其他调味料：胡椒粉", ["胡椒粉"], []),
    ("配料：生抽 + 老抽，蚝油", ["生抽", "老抽", "蚝油"], []),
    ("菜类材料：建议荤素搭配，选择自己喜欢的食材洗干净即可。例如：", [], []),
    (
        "面食材料：可以是手工面条、龙须面、面鱼，也可以是泡面面饼、各类规格粉丝，"
        "或者是其他任何自己所喜欢的面食形式。",
        [], [],
    ),
    ("原则：万物皆可酿", [], []),
    ("其他：随便，不会影响到口味", [], []),
    ("糖：", [], []),
    ("调味料：", [], []),
])
def test_kitchen_equipment_ingredient_lines(importer, line, names, groups):
    rows, equipment, _ = importer._parse_ingredient_section(line)
    assert [row["ingredient_name"] for row in rows] == names
    assert equipment == groups


@pytest.mark.parametrize("line,expected", [
    ("高筋面粉：400g", [("高筋面粉", "400", "g")]),
    ("水: 120g", [("水", "120", "g")]),
    ("③**辅料**：`盐` 2g、糖（3g，调味用）", [("盐", "2", "g"), ("糖", "3", "g")]),
])
def test_ingredient_colon_name_preserves_quantity(importer, line, expected):
    rows, equipment, unclassified = importer._parse_ingredient_section(line)
    assert [(row["ingredient_name"], row["quantity"], row["unit"]) for row in rows] == expected
    assert equipment == unclassified == []


@pytest.mark.parametrize("line,subject,unclassified", [
    ("蒸鱼盘子（能平放下一条鱼即可）", "蒸鱼盘子", ["蒸鱼盘子"]),
    ("家庭铁勺子", "家庭铁勺子", ["家庭铁勺子"]),
    ("砵或者有一定深度的碗", "砵", []),
    ("工具：`锅`（砂锅为宜，铝锅其次，高压锅也可以，最好不要铁锅、铜锅）", "锅", []),
    ("工具：**铁锅**", "铁锅", []),
    ("⑦喷壶：使面团或容器表面均匀覆盖上水或油，用于烤制脆皮和防粘。", "喷壶", ["喷壶"]),
    ("⑧筛子：使面粉均匀铺开或过滤面粉结块和杂质。", "筛子", ["筛子"]),
    ("⑩刷子：用于给面团刷蛋液，使成品更加光鲜、亮丽、有光泽。", "刷子", ["刷子"]),
])
def test_kitchen_equipment_tool_subjects(importer, line, subject, unclassified):
    assert importer._tool_subject(line) == (subject, False)
    assert importer._parse_ingredient_section(line) == ([], [], unclassified)


@pytest.mark.parametrize("line,name,optional", [
    ("必备：东北米（金龙鱼 30 元 5kg 的就行）", "东北米", False),
    ("可选：香菜", "香菜", True),
    ("④可选: 香菜", "香菜", True),
    ("花椒：可选", "花椒", True),
    ("鸡精：可选", "鸡精", True),
])
def test_kitchen_equipment_ingredient_prefixes(importer, line, name, optional):
    rows, equipment, unclassified = importer._parse_ingredient_section(line)
    assert [(row["ingredient_name"], row["is_optional"]) for row in rows] == [(name, optional)]
    assert equipment == unclassified == []


@pytest.mark.parametrize("step,groups", [
    ("放入预热好的烤箱，200 度烤 15 分钟", [["oven"]]),
    ("也可以用高压锅压 20 分钟", []),
    ("放入蒸锅大火蒸 8 分钟", [["steamer"]]),
    ("小贴士：隔夜可用烤箱回温", []),
    ("盖上锅盖，转中小火炖煮 50 分钟-60 分钟（高压锅则为 40 分钟）", []),
    ("放入烤箱 (也可以用微波炉。)", [["oven"]]),
])
def test_kitchen_equipment_step_lines(importer, step, groups):
    assert importer._step_equipment(step) == groups


def test_kitchen_equipment_title_and_merge(importer, tmp_path):
    recipe = tmp_path / "recipe.md"
    recipe.write_text(
        "# 微波炉鸡蛋羹的做法\n\n## 必备原料和工具\n"
        "- 烤箱或电饭锅\n\n## 操作步骤\n- 放入烤箱\n"
        "### 小贴士\n可以用蒸锅。\n放入砂锅\n"
        "## 附加内容\n- 高压锅\n",
        encoding="utf-8",
    )
    assert importer.parse_recipe_md(str(recipe))["equipment"] == [["microwave"], ["oven"]]


def test_optional_equipment_is_still_classified_as_tool(importer):
    assert importer._parse_ingredient_section(
        "可选：空气炸锅烤架（用烤架油比较少）"
    ) == ([], [], ["空气炸锅烤架"])


def test_import_replaces_equipment_and_preserves_fork(importer, tmp_path, db, capsys):
    from stock_manager.api.equipment_services import load_recipe_equipment
    from stock_manager.api.recipe_services import fork_recipe

    url, session = db
    recipe_path = tmp_path / "dishes" / "soup" / "recipe.md"
    recipe_path.parent.mkdir(parents=True)
    markdown = (
        "# Soup\n\n## 必备原料和工具\n"
        "- 烤箱或电饭锅\n- 2 个大碗\n- 盐（出锅调味）\n"
        "\n## 操作步骤\n- 加水\n"
    )
    recipe_path.write_text(markdown, encoding="utf-8")
    assert importer.import_howtocook(str(tmp_path), url) == _counts(imported=1)
    recipe = session.query(Recipe).filter_by(source_type="howtocook").one()
    assert load_recipe_equipment(session, [recipe.id]) == {recipe.id: [["oven", "rice_cooker"]]}
    assert [row.ingredient_name for row in recipe.ingredients] == ["盐"]
    output = capsys.readouterr().out
    assert (
        "equipment: recipes 1, groups 1; per code: oven 1, air_fryer 0, microwave 0, "
        "pressure_cooker 0, rice_cooker 1, steamer 0, blender 0, electric_mixer 0, "
        "bread_machine 0, clay_pot 0, grill 0, thermometer 0, kitchen_scale 0; "
        "unclassified tool lines 1"
    ) in output
    assert "  ? dishes/soup/recipe.md: 大碗" in output

    fork_id = fork_recipe(session, recipe.id).id
    recipe_path.write_text(markdown.replace("烤箱或电饭锅", "砂锅"), encoding="utf-8")
    assert importer.import_howtocook(str(tmp_path), url) == _counts(existing=1)
    assert load_recipe_equipment(session, [recipe.id, fork_id]) == {
        recipe.id: [["clay_pot"]],
        fork_id: [["oven", "rice_cooker"]],
    }


def test_equipment_groups_follow_section_order_and_skip_nested_tips(importer, tmp_path):
    recipe = tmp_path / "recipe.md"
    recipe.write_text(
        "# Soup\n\n## 必备原料和工具\n- 微波炉\n"
        "### 小贴士\n- 面包机\n#### 清洗\n- 烧烤炉\n"
        "## 操作步骤\n- 用蒸锅蒸熟\n"
        "## 工具\n- 砂锅\n",
        encoding="utf-8",
    )
    parsed = importer.parse_recipe_md(str(recipe))
    assert parsed["equipment"] == [["microwave"], ["steamer"], ["clay_pot"]]


@pytest.mark.parametrize(("line", "name", "quantity", "unit"), [
    ("皮蛋 2 个", "皮蛋", "2", "个"),
    ("白砂糖 2.5g", "白砂糖", "2.5", "g"),
    ("生抽 15 ml", "生抽", "15", "ml"),
    ("清水 = 50g", "清水", "50", "g"),
    ("西红柿 = 1 个", "西红柿", "1", "个"),
    ("蒜瓣: 2-3 个", "蒜瓣", "2-3", "个"),
    ("食用油：100ml", "食用油", "100", "ml"),
    ("盐 (15g)", "盐", "15", "g"),
    ("盐量 = 份数 * 3g", "盐", "3", "g"),
    ("青辣椒 = 份数 * 0.5 个", "青辣椒", "0.5", "个"),
    ("辣椒的数量 = 1.5 只/三人", "辣椒", "1.5", "只"),
    ("大葱 = 半颗", "大葱", "半", "颗"),
    ("包菜 半 颗", "包菜", "半", "颗"),
    ("糖 2～3g", "糖", "2-3", "g"),
    ("辣椒 2~3 根", "辣椒", "2-3", "根"),
    ("油 10-15ml", "油", "10-15", "ml"),
    ("白胡椒粉 5g-10g", "白胡椒粉", "5-10", "g"),
    ("白胡椒粉 5g - 10g", "白胡椒粉", "5-10", "g"),
    ("排骨 250g 到 500g", "排骨", "250-500", "g"),
    ("叶菜类蔬菜：300g ~ 500g", "叶菜类蔬菜", "300-500", "g"),
    ("橄榄油：10ml - 15ml", "橄榄油", "10-15", "ml"),
    ("米：100ml-200ml/人", "米", "100-200", "ml"),
    ("鸡蛋 3 - 4 个", "鸡蛋", "3-4", "个"),
    ("鸡蛋 3 - 4", "鸡蛋", "3-4", None),
    ("姜，13g。", "姜", "13", "g"),
    ("醋", "醋", None, None),
])
def test_calculation_ingredient_formats(importer, line, name, quantity, unit):
    rows, unparsed = importer._parse_calculations("  - " + line)
    assert [(r["ingredient_name"], r["quantity"], r["unit"]) for r in rows] == [(name, quantity, unit)]
    assert not unparsed


@pytest.mark.parametrize("table,expected", [
    ("| 材料 | 用量 |\n| --- | --- |\n| 低筋面粉 | 40g |\n| 鸡蛋 | 2 个 |",
     [("低筋面粉", "40", "g"), ("鸡蛋", "2", "个")]),
    ("| 原料 | 数量 | 单位 |\n| :-- | --: | --- |\n| 猪肘 | 1 | 只 |\n| 油 | 200 | ml |",
     [("猪肘", "1", "只"), ("油", "200", "ml")]),
])
def test_calculation_tables(importer, table, expected):
    rows, unparsed = importer._parse_calculations(table)
    assert [(r["ingredient_name"], r["quantity"], r["unit"]) for r in rows] == expected
    assert not unparsed


def test_calculation_alternatives_and_explanation_lines(importer):
    text = """### 小标题
普通段落
> - 鸡蛋 3 个
- 注：推荐红葱
- 每次制作前先搅拌
- 每份都要调味
- 总量只供参考
- 使用上述条件变更
- 一份正好够吃
- 以上仅供参考
- 份数根据情况调整
- 1 → 2 个
1. 干木耳: 20g / 湿木耳: 120g
"""
    rows, unparsed = importer._parse_calculations(text)
    assert [(r["ingredient_name"], r["quantity"], r["is_optional"]) for r in rows] == [
        ("干木耳", "20", False), ("湿木耳", "120", True),
    ]
    assert not unparsed


@pytest.mark.parametrize("line,expected", [
    ("料酒、盐、冰糖、植物油", [("料酒", False), ("盐", False), ("冰糖", False), ("植物油", False)]),
    ("剑骨鱼或鲤鱼", [("剑骨鱼", False), ("鲤鱼", True)]),
    ("茉莉绿茶茶叶/苏打气泡水二选一", [("茉莉绿茶茶叶", True), ("苏打气泡水", True)]),
    ("烤鹰嘴豆粉— 可用炒熟的鹰嘴豆磨粉替代", [("烤鹰嘴豆粉", False)]),
    ("豆腐—可选但强烈推荐", [("豆腐", True)]),
])
def test_required_ingredient_lists(importer, line, expected):
    assert [(r["ingredient_name"], r["is_optional"]) for r in importer._parse_ingredients(line)] == expected


@pytest.mark.parametrize("line,expected", [
    ("小葱 3-", ("小葱", "3", None)),
    ("蒜 2 瓣", ("蒜", "2", "瓣")),
    ("干小米椒🌶", ("干小米椒", None, None)),
    ("鸡蛋 **", ("鸡蛋", None, None)),
    ("百味来  拿坡里意面酱", ("百味来 拿坡里意面酱", None, None)),
    ("排骨 250g 到 500g", ("排骨", "250-500", "g")),
])
def test_ingredient_name_cleanup(importer, line, expected):
    assert [(r["ingredient_name"], r["quantity"], r["unit"]) for r in importer._parse_ingredients(line)] == [expected]


@pytest.mark.parametrize("required,computed,expected", [
    ("- 蒜", "- 大蒜 3 瓣", [("蒜", "3", "瓣")]),
    ("- 海参\n- 葱白", "- 蚝油 20g\n- 生抽 10ml",
     [("海参", None, None), ("葱白", None, None), ("蚝油", "20", "g"), ("生抽", "10", "ml")]),
    ("- 葱、姜、油", "- 姜片 = 10g\n- 蚝油 20g",
     [("葱", None, None), ("姜", None, None), ("油", None, None), ("姜片", "10", "g"), ("蚝油", "20", "g")]),
    ("- 盐\n- 盐 2g", "- 盐 3g", [("盐", "3", "g")]),
    ("- 百味来  拿坡里意面酱", "- 百味来拿坡里意面酱 1 罐",
     [("百味来 拿坡里意面酱", "1", "罐")]),
    ("- 百味来拿坡里意面酱", "- 百味来  拿坡里意面酱 1 罐",
     [("百味来拿坡里意面酱", "1", "罐")]),
    ("- 生抽", "- 生抽 15ml\n- 老抽 3ml",
     [("生抽", "15", "ml"), ("老抽", "3", "ml")]),
])
def test_recipe_merges_calculations(importer, tmp_path, required, computed, expected):
    source = tmp_path / "recipe.md"
    source.write_text(
        f"# 试菜\n\n## 必备原料和工具\n{required}\n\n## 计算\n{computed}\n", encoding="utf-8",
    )
    rows = importer.parse_recipe_md(str(source))["ingredients"]
    assert [(r["ingredient_name"], r["quantity"], r["unit"]) for r in rows] == expected
    assert [row["sort_order"] for row in rows] == list(range(len(expected)))


def test_nested_steps_and_image_only_bullets(importer):
    markdown = """# 油焖大虾
![封面](cover.png)

## 操作步骤
1. 清洗大虾
2. 剪去虾须
3. 准备调料：
  - 黄酒 30g
  - 水两小碗
  - 盐 3g
  - 冰糖 10 克
  - ![调料](sauce.png)
- ![调料完成](sauce-ready.png)
4. 起锅热油
5. 炒香葱姜
6. 翻炒大虾
7. 淋入料汁
8. 盖锅焖煮
9. 收汁
10. 装盘
"""
    steps = importer._parse_steps(dict(importer._recipe_sections(markdown))["steps"])
    assert [row["step_number"] for row in steps] == list(range(1, 11))
    assert steps[2]["instruction"] == "准备调料：黄酒 30g；水两小碗；盐 3g；冰糖 10 克"
    assert importer._photo_steps(markdown, list(range(1, 11))) == [
        ("封面", "cover.png", None), ("调料", "sauce.png", 3), ("调料完成", "sauce-ready.png", 3),
    ]


def test_step_emphasis_and_continuation(importer):
    text = """- **要求**：在开火前准备
  - 使用 **中火** 和`平底锅`
    倒入*热油*后转小火
普通续段用_小火_
- 出锅
"""
    assert [row["instruction"] for row in importer._parse_steps(text)] == [
        "要求：在开火前准备：使用 中火 和平底锅 倒入热油后转小火；普通续段用小火",
        "出锅",
    ]
    assert importer._clean_line("**中火**") == "中火"
    assert [row["instruction"] for row in importer._parse_steps("加热\n翻炒\n\n装盘")] == ["加热 翻炒", "装盘"]


@pytest.mark.parametrize("line,expected", [
    ("放入预热至 180 度的烤箱中，烤 30-40 分钟或至熟", [["oven"]]),
    ("也可以用高压锅压 20 分钟", []),
    ("烤箱或空气炸锅", []),
    ("烤箱或者平底锅", []),
    ("平底锅 / 烤箱", []),
    ("空气炸锅可以代替烤盘", []),
    ("没有的话，用微波炉加热", []),
    ("放入烤箱，或至熟，另也可以用高压锅", [["oven"]]),
])
def test_equipment_step_alternatives_are_local(importer, line, expected):
    assert importer._step_equipment(line) == expected


@pytest.mark.parametrize("code,ingredients,steps,extra", [
    ("ingredient_markup", ["盐🌶"], ["装盘"], {}),
    ("ingredient_punct", ["盐、胡椒"], ["装盘"], {}),
    ("ingredient_digit", ["2号盐"], ["装盘"], {}),
    ("ingredient_long", ["一二三四五六七八九十非常长"], ["装盘"], {}),
    ("ingredient_duplicate", ["盐", "盐"], ["装盘"], {}),
    ("ingredient_duplicate", ["百味来 拿坡里意面酱", "百味来拿坡里意面酱"], ["装盘"], {}),
    ("step_markup", ["盐"], ["用**大火**"], {}),
    ("step_empty", ["盐"], [" "], {}),
    ("recipe_empty", ["盐"], [], {}),
    ("calc_unparsed", ["盐"], ["装盘"], {"calc_unparsed": ["2g"]}),
    ("override_stale", ["盐"], ["装盘"], {"override_stale": True}),
])
def test_audit_error_codes(importer, code, ingredients, steps, extra):
    recipe = {
        "ingredients": [{"ingredient_name": name, "quantity": None} for name in ingredients],
        "steps": [{"step_number": i, "instruction": text} for i, text in enumerate(steps, start=1)],
        "raw_markdown": "",
        "equipment": [],
        **extra,
    }
    errors = [found for found, _ in importer._audit_recipe(recipe) if found in importer._ERROR_CODES]
    assert errors == [code]


def test_audit_cli_report_is_offline_and_fails_on_errors(importer, tmp_path, monkeypatch, capsys):
    recipe = tmp_path / "dishes/soup/test.md"
    recipe.parent.mkdir(parents=True)
    recipe.write_text(
        "# 测试汤\n![封面](cover.jpg)\n## 必备原料\n- 盐\n"
        "## 计算\n- 2g\n## 操作步骤\n- 放入烤箱![烘烤](step.jpg)\n",
        encoding="utf-8",
    )
    report = tmp_path / "review.md"
    monkeypatch.setattr("sys.argv", ["import_howtocook.py", "--audit", str(tmp_path), "--report", str(report)])

    def unexpected(*args, **kwargs):
        pytest.fail("Audit must not use the environment file or database")

    monkeypatch.setattr(importer, "_load_env", unexpected)
    monkeypatch.setattr(importer, "_get_db_session", unexpected)
    with pytest.raises(SystemExit) as result:
        importer.main()
    assert result.value.code == 1
    output = capsys.readouterr().out
    assert "calc_unparsed: 1" in output
    assert "calc_unparsed  dishes/soup/test.md  2g" in output
    review = report.read_text(encoding="utf-8")
    assert "## 测试汤" in review and "dishes/soup/test.md" in review
    assert "| 盐 |  |  | Yes | No |" in review
    assert "1. 放入烤箱" in review and "- oven" in review
    assert "Cover: 封面" in review and "Step 1: 烘烤" in review
    assert "`ingredient_no_quantity`: 盐" in review


def test_recipe_override_applies_to_import_and_audit(
    importer, tmp_path, db, monkeypatch, capsys, reviewed_aliases,
):
    root = tmp_path / "source"
    source = root / "dishes" / "soup" / "test.md"
    source.parent.mkdir(parents=True)
    source.write_text("# 原标题\n## 必备原料\n- 盐\n## 操作\n- 使用烤箱\n## 附加内容\n锅中加糖\n", encoding="utf-8")
    key = source.relative_to(root).as_posix()
    entry = {
        "reason": "Use the alternate preparation recorded in this fixture.",
        "sha256": sha256(source.read_bytes()).hexdigest(),
        "title": "新标题",
        "ingredients": [{"ingredient_name": "糖", "quantity": "2", "unit": "克", "normalized_name": "白糖"}],
        "steps": ["锅中加糖"],
        "equipment": [],
    }
    override_file = tmp_path / "overrides.json"
    override_file.write_text(json.dumps({key: entry}), encoding="utf-8")
    monkeypatch.setattr(importer, "_OVERRIDE_PATH", override_file)
    whitelist = tmp_path / "ingredient_names.txt"
    whitelist.write_text("", encoding="utf-8")
    monkeypatch.setattr(importer, "_INGREDIENT_NAMES_PATH", whitelist)

    report = tmp_path / "review.md"
    assert importer.audit_howtocook(root, report) == 0
    review = report.read_text(encoding="utf-8")
    assert "## 新标题" in review and "| 糖 | 2 | 克 | No | No |" in review
    assert "1. 锅中加糖" in review
    assert "`equipment_mentioned_not_required`: oven" in review

    url, session = db
    assert importer.import_howtocook(str(root), url)["imported"] == 1
    loaded = session.query(Recipe).one()
    assert loaded.title == "新标题"
    assert [(row.ingredient_name, row.normalized_name) for row in loaded.ingredients] == [("糖", "白糖")]
    assert [step.instruction for step in loaded.steps] == ["锅中加糖"]

    source.write_text(source.read_text(encoding="utf-8") + "\n## 附加内容\n已修改\n", encoding="utf-8")
    assert importer.audit_howtocook(root, report) == 1
    assert "override_stale  dishes/soup/test.md" in capsys.readouterr().out
    assert "## 原标题" in report.read_text(encoding="utf-8")
    assert importer.import_howtocook(str(root), url)["existing"] == 1
    assert "override_stale (source SHA-256 differs)" in capsys.readouterr().out
    session.expire_all()
    assert loaded.title == "原标题"
    assert [row.ingredient_name for row in loaded.ingredients] == ["盐"]
    assert [step.instruction for step in loaded.steps] == ["使用烤箱"]


@pytest.mark.parametrize("line,expected", [
    ("- 黑鳕鱼，带皮，2 片，450g", [("黑鳕鱼", "2", "片")]),
    ("- 生粉 2 1/2 茶匙", [("生粉", "2 1/2", "茶匙")]),
    ("- 1 汤匙 = 15ml\n- 盐 1/4 茶匙", [("盐", "1/4", "茶匙")]),
    ("- 生抽 75g = 15g * 5", [("生抽", "75", "g")]),
    ("- 橄榄油 7 x 5 =35g，", [("橄榄油", "35", "g")]),
    ("- 干辣椒 = 5，6 个", [("干辣椒", "5-6", "个")]),
])
def test_calculation_quantities_with_notes_and_formulas(importer, line, expected):
    rows, unparsed = importer._parse_calculations(line)
    assert [(r["ingredient_name"], r["quantity"], r["unit"]) for r in rows] == expected
    assert not unparsed


@pytest.mark.parametrize("text,expected,unparsed", [
    ("小葱：约 30g（3-4 根），葱白切段备用", [("小葱", "30", "g")], []),
    ("鸡蛋 = 1.5 个 * 份数，向上取整", [("鸡蛋", "1.5", "个")], []),
    ("食用油 = 4ml * 鸡蛋/个", [("食用油", "4", "ml")], []),
    ("大蒜：约 25g（5-6 瓣），中间切开备用", [("大蒜", "25", "g")], []),
    ("香菜按照个人口味", [], ["香菜按照个人口味"]),
    ("500ml 水", [], ["500ml 水"]),
    ("鱼 建议新手以一条中等大小的鲫鱼上手", [("鱼", None, None)], []),
    ("新鲜鸡蛋 1 个", [("鸡蛋", "1", "个")], []),
    ("糖浆 ⅛ cup", [("糖浆", "⅛", "cup")], []),
    ("盐 ⅓ 茶匙", [("盐", "⅓", "茶匙")], []),
    ("水 ⅔ cup", [("水", "⅔", "cup")], []),
    ("葱、姜 3g，切段备用", [("葱", "3", "g"), ("姜", "3", "g")], []),
])
def test_calculation_keeps_names_before_quantities(importer, text, expected, unparsed):
    rows, rejected = importer._parse_calculations(f"- {text}")
    assert [(r["ingredient_name"], r["quantity"], r["unit"]) for r in rows] == expected
    assert rejected == unparsed


def test_step_method_headings_preserve_tips(importer):
    steps = importer._parse_steps(
        "### **方法一 - 平底锅**\n\n1. 热锅\n> 小心热油\n\n"
        "### 方法二 - 微波炉\n\n1. 加热\n> 用合适的碗\n2. 吃\n> 趁热吃\n",
    )
    assert [r["instruction"] for r in steps] == [
        "【方法一 - 平底锅】热锅；小心热油", "【方法二 - 微波炉】加热；用合适的碗", "吃；趁热吃",
    ]


@pytest.mark.parametrize("tool", [
    "密封袋", "牛轧糖模具", "港式奶茶过滤袋", "陶瓷容器", "筷子一双", "蒸锅用水", "杯子", "例如带刻度的杯子",
    "陶瓷杯", "保温杯", "筛网", "过滤网", "滤网", "烤网", "雪克瓶", "圆碟子，直径 28cm", "直径 28cm",
])
def test_required_and_calculation_tools_do_not_become_ingredients(importer, tool):
    assert importer._parse_ingredients(f"- {tool}") == []
    assert importer._parse_calculations(f"- {tool}") == ([], [])


def test_reviewed_aliases_merge_only_same_pairs(importer, tmp_path, reviewed_aliases):
    reviewed_aliases(same=[["茄子", "长的上小下大的茄子"]], different=[["豆腐", "日本豆腐"]])
    source = tmp_path / "test.md"
    source.write_text(
        "# 测试\n## 必备原料\n- 茄子\n- 豆腐\n## 计算\n- 长的上小下大的茄子 100g\n- 日本豆腐 2 个\n",
        encoding="utf-8",
    )
    parsed = importer.parse_recipe_md(str(source))
    assert [(row["ingredient_name"], row["quantity"]) for row in parsed["ingredients"]] == [
        ("茄子", "100"), ("豆腐", None), ("日本豆腐", "2"),
    ]
    assert "ingredient_maybe_duplicate" not in {code for code, _ in importer._audit_recipe(parsed)}


@pytest.mark.parametrize("code,bad,good,known", [
    ("ingredient_prose", ["姜切段备用"], ["姜"], {"姜切段备用", "姜"}),
    ("ingredient_prose", ["例如加盐"], ["盐"], None),
    ("ingredient_prose", ["比如白糖"], ["白糖"], None),
    ("ingredient_prose", ["直径"], ["小葱"], None),
    ("ingredient_prose", ["额外的食材"], ["葱"], None),
    ("ingredient_prose", ["用作调味的食材"], ["葱"], None),
    ("ingredient_prose", ["点缀的食材"], ["葱"], None),
    ("ingredient_tool", ["雪克瓶"], ["瓶装椰子汁"], None),
    ("ingredient_tool", ["滤网"], ["牛奶"], None),
    ("ingredient_tool", ["港式奶茶过滤袋"], ["袋泡红茶"], {"港式奶茶过滤袋", "袋泡红茶"}),
    ("ingredient_unknown", ["虚构食材"], ["盐"], {"盐"}),
    ("ingredient_maybe_duplicate", ["豌豆", "青豌豆"], ["豆腐", "日本豆腐"], {"豌豆", "青豌豆", "豆腐", "日本豆腐"}),
])
def test_round_two_audit_ingredient_codes(importer, code, bad, good, known):
    def codes(names):
        recipe = {
            "ingredients": [{"ingredient_name": name, "quantity": None} for name in names],
            "steps": [{"step_number": 1, "instruction": "吃"}],
            "equipment": [], "raw_markdown": "", "ingredient_source": "",
        }
        return {found for found, _ in importer._audit_recipe(recipe, known)}

    assert code in codes(bad)
    assert code not in codes(good)


@pytest.mark.parametrize("override_fields,stale,expected", [
    ({"ingredients": [{"ingredient_name": "香菜"}]}, False, set()),
    ({"ingredients": [{"ingredient_name": "香菜"}]}, True, {"calc_unparsed", "override_stale"}),
    ({"steps": ["吃"]}, False, {"calc_unparsed"}),
    ({"equipment": []}, False, {"calc_unparsed"}),
])
def test_calculation_diagnostics_require_a_valid_ingredient_replacement(
    importer, tmp_path, override_fields, stale, expected,
):
    path = tmp_path / "recipe.md"
    path.write_text(
        "# 测试\n## 必备原料\n- 香菜\n## 计算\n- 香菜按照个人口味\n## 操作\n1. 吃\n",
        encoding="utf-8",
    )
    override = {"sha256": "invalid" if stale else sha256(path.read_bytes()).hexdigest(), **override_fields}
    recipe = importer.parse_recipe_md(str(path), override)
    errors = {code for code, _ in importer._audit_recipe(recipe) if code in importer._ERROR_CODES}
    assert errors == expected
    assert recipe["steps"] == [{"step_number": 1, "instruction": "吃"}]


@pytest.mark.parametrize("replacement,error", [
    ("【方法一】煮面；调味", False),
    ("享用煮好的面条", True),
])
def test_override_audit_rejects_reworded_steps(importer, tmp_path, replacement, error):
    path = tmp_path / "recipe.md"
    path.write_text(
        "# 测试\n## 必备原料\n- 盐\n## 操作\n### 方法一\n- 煮面\n  - 调味\n",
        encoding="utf-8",
    )
    recipe = importer.parse_recipe_md(
        str(path), {"sha256": sha256(path.read_bytes()).hexdigest(), "steps": [replacement]},
    )
    errors = {code for code, _ in importer._audit_recipe(recipe) if code in importer._ERROR_CODES}
    assert ("override_text_not_in_source" in errors) is error
    if error:
        assert recipe["steps"][0]["instruction"] == "【方法一】煮面：调味"


@pytest.fixture
def reviewed_aliases(importer, tmp_path, monkeypatch):
    path = tmp_path / "aliases.json"

    def write(*, same=(), different=(), recipes=None):
        importer._load_aliases.cache_clear()
        path.write_text(
            json.dumps({"same": same, "different": different, "recipes": recipes or {}}),
            encoding="utf-8",
        )

    monkeypatch.setattr(importer, "_ALIASES_PATH", path)
    write()
    return write


def test_calculation_rejects_mismatched_range_units(importer):
    assert importer._parse_calculations("- 排骨 250g 到 500ml") == ([], ["排骨 250g 到 500ml"])


@pytest.mark.parametrize("punctuation,separator", [("。", ""), ("！", ""), ("？", ""), ("；", ""), ("", "；")])
def test_step_quote_join_respects_existing_punctuation(importer, punctuation, separator):
    steps = importer._parse_steps(f"1. 静置\n> 体积明显增大{punctuation}\n> 发酵失败了？")
    assert [step["instruction"] for step in steps] == [
        f"静置；体积明显增大{punctuation}{separator}发酵失败了？",
    ]


def test_step_tip_intro_preserves_the_preceding_full_stop(importer):
    steps = importer._parse_steps(
        "1. 最终的面糊应该是表面有很多气泡的且体积明显增大。\n\n"
        "**发酵失败了？看看这里：**\n\n> 确定酵母没有过期\n\n2. 揉面",
    )
    assert steps[0]["instruction"].startswith(
        "最终的面糊应该是表面有很多气泡的且体积明显增大。发酵失败了？看看这里：",
    )
    assert "确定酵母没有过期" in steps[0]["instruction"]


@pytest.mark.parametrize("with_required", [True, False])
def test_same_aliases_merge_transitively(importer, tmp_path, reviewed_aliases, with_required):
    reviewed_aliases(same=[["快熟面", "风干快熟面"], ["任何牌子的快熟面", "快熟面"]])
    path = tmp_path / "recipe.md"
    required = "## 必备原料\n- 风干快熟面\n" if with_required else ""
    path.write_text(
        f"# 拌面\n{required}## 计算\n- 任何牌子的快熟面 1 块\n- 风干快熟面\n## 操作\n- 煮熟\n",
        encoding="utf-8",
    )
    parsed = importer.parse_recipe_md(str(path))
    expected_name = "风干快熟面" if with_required else "任何牌子的快熟面"
    assert [(row["ingredient_name"], row["quantity"]) for row in parsed["ingredients"]] == [(expected_name, "1")]


@pytest.mark.parametrize("calculation,expected_pair", [
    ("- 生抽 15ml\n- 老抽 3ml", {"生抽", "老抽"}),
    ("- 姜 2g\n- 姜沫 3g", {"姜", "姜沫"}),
])
def test_audit_demands_review_of_synonyms_and_single_character_names(
    importer, tmp_path, reviewed_aliases, calculation, expected_pair,
):
    path = tmp_path / "recipe.md"
    path.write_text(f"# 测试\n## 计算\n{calculation}\n## 操作\n- 调味\n", encoding="utf-8")

    def issues():
        parsed = importer.parse_recipe_md(str(path))
        assert {row["ingredient_name"] for row in parsed["ingredients"]} == expected_pair
        return [(code, detail) for code, detail in importer._audit_recipe(parsed) if code in importer._ERROR_CODES]

    [(code, detail)] = issues()
    assert code == "ingredient_maybe_duplicate"
    assert set(detail.split(" / ")) == expected_pair
    reviewed_aliases(different=[sorted(expected_pair)])
    assert issues() == []


@pytest.mark.parametrize("resolution,expected", [
    ("none", ["calc_repeated_name"]),
    ("steps", ["calc_repeated_name"]),
    ("stale", ["calc_repeated_name", "override_stale"]),
    ("sum", []),
])
def test_repeated_calculation_needs_reviewed_ingredient_override(importer, tmp_path, resolution, expected):
    path = tmp_path / "recipe.md"
    path.write_text(
        "# 草莓冰淇淋\n## 必备原料\n- 香草精\n## 计算\n### 草莓糖浆\n- 香草精 1 克\n"
        "### 冰淇淋底料\n- 香草 精 5 克\n## 操作\n- 冷冻\n",
        encoding="utf-8",
    )
    override = None
    if resolution in {"sum", "stale"}:
        override = {
            "sha256": sha256(path.read_bytes()).hexdigest() if resolution == "sum" else "stale",
            "reason": "Add the syrup and base amounts.",
            "ingredients": [{"ingredient_name": "香草精", "quantity": "6", "unit": "克"}],
        }
    elif resolution == "steps":
        override = {"sha256": sha256(path.read_bytes()).hexdigest(), "steps": ["冷冻"]}

    recipe = importer.parse_recipe_md(str(path), override)
    errors = [(code, detail) for code, detail in importer._audit_recipe(recipe) if code in importer._ERROR_CODES]
    assert [code for code, _ in errors] == expected
    if resolution == "sum":
        assert [(row["ingredient_name"], row["quantity"], row["unit"]) for row in recipe["ingredients"]] == [
            ("香草精", "6", "克"),
        ]
    else:
        assert errors[0] == ("calc_repeated_name", "香草精: 1 克, 5 克")


@pytest.mark.parametrize("unit,bad", [
    ("cm", True), ("mm", True), ("厘米", True), ("毫米", True), ("寸", True),
    ("W", True), ("℃", True), ("°C", True), ("g", False), ("根", False), (None, False),
])
def test_audit_rejects_dimension_and_temperature_units(importer, unit, bad):
    recipe = {
        "ingredients": [{"ingredient_name": "葱", "quantity": "10", "unit": unit}],
        "steps": [{"step_number": 1, "instruction": "调味"}],
        "equipment": [],
        "raw_markdown": "",
    }
    errors = [code for code, _ in importer._audit_recipe(recipe) if code in importer._ERROR_CODES]
    assert errors == (["ingredient_bad_unit"] if bad else [])


@pytest.mark.parametrize("quantity,unit,expected", [
    ("一个", None, None),
    ("水饺体积的两倍", None, None),
    (1, None, None),
    ("一", "个", "一"),
    ("1/2", "个", "1/2"),
    ("3 - 4", "个", "3-4"),
])
def test_audit_validates_override_quantity_format(importer, tmp_path, quantity, unit, expected):
    path = tmp_path / "recipe.md"
    path.write_text("# 测试\n## 必备原料\n- 玉米 2 个\n## 操作\n- 水煮\n", encoding="utf-8")
    recipe = importer.parse_recipe_md(str(path), {
        "sha256": sha256(path.read_bytes()).hexdigest(),
        "ingredients": [{"ingredient_name": "玉米", "quantity": quantity, "unit": unit}],
    })
    errors = [code for code, _ in importer._audit_recipe(recipe) if code in importer._ERROR_CODES]
    assert errors == (["override_quantity_format"] if expected is None else [])
    assert recipe["ingredients"][0]["quantity"] == (expected or "2")


def test_audit_flags_unused_review_entries(importer, tmp_path, reviewed_aliases):
    reviewed_aliases(same=[["蒜", "大蒜"]], different=[["姜", "姜片"], ["生抽", "老抽"]])
    path = tmp_path / "recipe.md"
    path.write_text("# 测试\n## 必备原料\n- 蒜、姜、姜片、生抽\n## 计算\n- 大蒜 3 瓣\n", encoding="utf-8")
    recipe = importer.parse_recipe_md(str(path))
    assert [row["ingredient_name"] for row in recipe["ingredients"]] == ["蒜", "姜", "姜片", "生抽"]

    # An alias still counts as used after the parser has merged its two names.
    other = {"ingredients": [{"ingredient_name": "老抽"}]}
    assert list(importer._audit_review_tables([recipe, other], {"蒜", "大蒜", "老抽"})) == [
        ("alias_unused", "生抽 / 老抽"),
        ("whitelist_unused", "大蒜"),
    ]
    assert list(importer._audit_review_tables(
        [{**recipe, "ingredients": recipe["ingredients"] + other["ingredients"]}], {"蒜", "老抽"},
    )) == []


def test_recipe_aliases_take_precedence_on_import(importer, tmp_path, db, reviewed_aliases):
    key = "dishes/vegetable_dish/日本豆腐煲.md"
    other = "dishes/vegetable_dish/其他豆腐煲.md"
    reviewed_aliases(
        different=[["日本豆腐", "豆腐"]],
        recipes={key: {"same": [["日本豆腐", "豆腐"]]}},
    )
    markdown = "# {title}\n## 必备原料\n- 日本豆腐\n## 计算\n- 豆腐 2 袋\n## 操作\n- 炖煮\n"
    for path in (key, other):
        source = tmp_path / path
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(markdown.format(title=source.stem), encoding="utf-8")

    url, session = db
    assert importer.import_howtocook(str(tmp_path), url)["imported"] == 2
    scoped = session.query(Recipe).filter_by(title="日本豆腐煲").one()
    unscoped = session.query(Recipe).filter_by(title="其他豆腐煲").one()
    assert [(row.ingredient_name, row.quantity, row.unit) for row in scoped.ingredients] == [
        ("日本豆腐", "2", "袋"),
    ]
    assert [(row.ingredient_name, row.quantity) for row in unscoped.ingredients] == [
        ("日本豆腐", None), ("豆腐", "2"),
    ]


def test_recipe_aliases_are_transitive_and_respect_local_different(importer, tmp_path, reviewed_aliases):
    same = "dishes/staple/拌面.md"
    different = "dishes/staple/汤面.md"
    reviewed_aliases(
        same=[["快熟面", "风干快熟面"], ["快熟面", "速煮面"]],
        recipes={
            same: {"same": [["快熟面", "任何牌子的快熟面"]]},
            different: {"different": [["风干快熟面", "速煮面"]]},
        },
    )
    source = tmp_path / "拌面.md"
    source.write_text(
        "# 拌面\n## 必备原料\n- 风干快熟面\n## 计算\n- 任何牌子的快熟面 1 块\n", encoding="utf-8",
    )
    rows = importer.parse_recipe_md(str(source), recipe_path=same)["ingredients"]
    assert [(row["ingredient_name"], row["quantity"]) for row in rows] == [("风干快熟面", "1")]

    source.write_text("# 汤面\n## 必备原料\n- 风干快熟面\n## 计算\n- 速煮面 1 块\n", encoding="utf-8")
    rows = importer.parse_recipe_md(str(source), recipe_path=different)["ingredients"]
    assert [row["ingredient_name"] for row in rows] == ["风干快熟面", "速煮面"]


def test_audit_flags_recipe_aliases_for_missing_paths_and_pairs(importer, tmp_path, reviewed_aliases):
    key = "dishes/soup/汤.md"
    absent = "dishes/soup/不存在.md"
    reviewed_aliases(recipes={
        key: {"same": [["香菇", "干香菇"]], "different": [["盐", "椒盐"]]},
        absent: {"same": [["香菇", "干香菇"]]},
    })
    source = tmp_path / "汤.md"
    source.write_text("# 汤\n## 必备原料\n- 香菇\n- 盐\n## 计算\n- 干香菇 20g\n", encoding="utf-8")
    parsed = importer.parse_recipe_md(str(source), recipe_path=key)
    assert list(importer._audit_review_tables([parsed], set())) == [
        ("alias_unused", f"{absent}: recipe path not found"),
        ("alias_unused", f"{key}: 椒盐 / 盐"),
    ]


@pytest.mark.parametrize("required,computed,classification,expected", [
    ("生抽", "老抽 3ml", "", "生抽 / 老抽"),
    ("辣椒", "干辣椒 5 个", "", "辣椒 / 干辣椒"),
    ("辣椒", "干辣椒 5 个", "same", None),
    ("辣椒", "干辣椒 5 个", "different", None),
    ("辣椒 2 个", "干辣椒 5 个", "", None),
    ("辣椒", "干辣椒", "", None),
    ("辣椒（也可用干辣椒）", "干辣椒 5 个", "", None),
    ("盐", "干辣椒 5 个", "", None),
])
def test_audit_unquantified_related_uses_both_source_sections(
    importer, tmp_path, reviewed_aliases, required, computed, classification, expected,
):
    path = tmp_path / "菜.md"
    key = "dishes/meat_dish/菜.md"
    if classification:
        reviewed_aliases(recipes={key: {classification: [["辣椒", "干辣椒"]]}})
    path.write_text(
        f"# 菜\n## 必备原料\n- {required}\n## 计算\n- {computed}\n## 操作\n- 炒\n", encoding="utf-8",
    )
    parsed = importer.parse_recipe_md(str(path), recipe_path=key)
    details = [detail for code, detail in importer._audit_recipe(parsed) if code == "ingredient_unquantified_related"]
    assert details == ([expected] if expected else [])


@pytest.mark.parametrize("line,override_kind,expected", [
    ("米酒 10 + 25 ml", "", True),
    ("米酒 10 + 25 ml", "ingredients", False),
    ("米酒 10 + 25 ml", "stale", True),
    ("米酒 10 + 25 ml", "steps", True),
    ("米酒 125g x 4= 500g", "", True),
    ("米酒 70 × 5 = 350g", "", True),
    ("米酒 7 * 5 = 35g", "", True),
    ("米酒 5-10 ml", "", False),
    ("米酒 5 ml * 份数", "", False),
])
def test_audit_calculation_arithmetic(importer, tmp_path, line, override_kind, expected):
    path = tmp_path / "菜.md"
    path.write_text(
        f"# 菜\n## 必备原料\n- 米酒\n## 计算\n- {line}\n## 操作\n- 加米酒\n", encoding="utf-8",
    )
    digest = sha256(path.read_bytes()).hexdigest()
    overrides = {
        "ingredients": {"sha256": digest, "ingredients": [{"ingredient_name": "米酒", "quantity": "35", "unit": "ml"}]},
        "stale": {"sha256": "stale", "ingredients": [{"ingredient_name": "米酒", "quantity": "35", "unit": "ml"}]},
        "steps": {"sha256": digest, "steps": ["加米酒"]},
    }
    recipe = importer.parse_recipe_md(str(path), overrides.get(override_kind))
    details = [detail for code, detail in importer._audit_recipe(recipe) if code == "calc_arithmetic"]
    assert details == ([f"- {line}"] if expected else [])


@pytest.mark.parametrize("opening,closing", [
    ("**工具**", "**辅料**"),
    ("工具：", "调味料："),
    ("**所需工具**", "### 面团"),
])
def test_tool_label_section_stops_at_the_next_label_or_heading(importer, opening, closing):
    text = f"- 中筋面粉\n\n{opening}\n\n- 烤箱\n- 披萨石（没有普通烤盘也可以）\n\n{closing}\n- 盐"
    rows, groups, unclassified = importer._parse_ingredient_section(text)
    assert [row["ingredient_name"] for row in rows] == ["中筋面粉", "盐"]
    assert groups == [["oven"]]
    assert unclassified == ["披萨石"]


def test_cucumber_and_pork_uses_the_required_cut_name(importer, tmp_path):
    path = tmp_path / "黄瓜炒肉.md"
    path.write_text(
        "# 黄瓜炒肉\n## 必备原料\n- 猪瘦肉\n## 计算\n- 猪肉 50 克\n## 操作\n- 炒熟\n",
        encoding="utf-8",
    )
    recipe = importer.parse_recipe_md(str(path), recipe_path="dishes/meat_dish/黄瓜炒肉.md")
    assert [(row["ingredient_name"], row["quantity"], row["unit"]) for row in recipe["ingredients"]] == [
        ("猪瘦肉", "50", "克"),
    ]
