from django.core.management import call_command


def test_openapi_schema_is_valid_and_warning_free(tmp_path):
    # Warnings usually mean an endpoint is documented wrongly (e.g. unknown
    # types), so they fail the build like errors do.
    call_command(
        "spectacular", "--validate", "--fail-on-warn", "--file", str(tmp_path / "schema.yaml")
    )
