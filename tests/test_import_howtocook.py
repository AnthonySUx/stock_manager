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

- 打散鸡蛋
- 下锅
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
    base = {"imported": 0, "existing": 0, "fixed": 0, "ingredients_synced": 0,
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
            ("剑骨鱼或鲤鱼", "1.5", "斤", 0),
            ("漓泉啤酒", "330", "ml", 1),
            ("黄油", None, None, 2),
            ("花椒", None, None, 3),
            ("鲜面条", None, None, 4),  # nested brackets from a markdown link
            ("色拉油 或 菜籽油", "1000", "ml", 5),  # only a note: its text is the name
            ("适量", None, None, 6),
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
        assert recipe.title == "口水鸡的做法"
        # Number and unit stored separately (#47); bracketed notes dropped from
        # names and the duplicate 盐 skipped (#49).
        assert [(i.ingredient_name, i.quantity, i.unit, i.sort_order) for i in recipe.ingredients] == [
            ("鸡蛋", "2", "个", 0), ("盐", None, None, 1), ("番茄", "1", "个", 2),
            ("鲤鱼", "1.5", "斤", 3),
        ]
        assert len(recipe.steps) == 2

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
