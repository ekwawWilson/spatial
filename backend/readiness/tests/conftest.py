import pytest

from readiness.defaults import DEFAULT_ITEMS
from readiness.models import Template, TemplateItem


@pytest.fixture(autouse=True)
def _default_template(db: None) -> None:
    """The platform default the data migration creates. Transactional tests
    elsewhere (the migration test) empty the tables when they finish, so put
    it back when it's missing."""
    if Template.objects.filter(district__isnull=True).exists():
        return
    template = Template.objects.create(name="Platform default", district=None)
    TemplateItem.objects.bulk_create(
        [TemplateItem(template=template, order=i, **item) for i, item in enumerate(DEFAULT_ITEMS)]
    )
