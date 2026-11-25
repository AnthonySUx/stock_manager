"""scripts/import_howtocook.py on a small fake HowToCook tree (#46).

No network and no real .env: the module is loaded with load_dotenv blocked,
and every run uses a throwaway SQLite file.
"""

import importlib.util
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
            (4, "撒上葱花"),
            (5, "小贴士：火不要太大"),
            (6, "盛出前尝一下咸淡"),
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
    ("糖 2～3g", "糖", "2～3", "g"),
    ("辣椒 2~3 根", "辣椒", "2~3", "根"),
    ("油 10-15ml", "油", "10-15", "ml"),
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
    ("step_markup", ["盐"], ["用**大火**"], {}),
    ("step_empty", ["盐"], [" 吃 "], {}),
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
