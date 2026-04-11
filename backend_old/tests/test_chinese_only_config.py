from app.api.v1.endpoints.config import get_default_config
from app.schemas.prompt_template import PromptTestRequest


def test_default_config_does_not_expose_output_language():
    config = get_default_config()

    assert "outputLanguage" not in config["otherConfig"]


def test_prompt_test_request_no_longer_accepts_output_language_field():
    assert "output_language" not in PromptTestRequest.model_fields
