import json
import os
import re
import uuid

from dotenv import load_dotenv
from loguru import logger
from openai import AsyncOpenAI

load_dotenv()

client = AsyncOpenAI()
MODEL = "gpt-5-nano"


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

FR_NFR_SYSTEM_PROMPT = """You are an expert business analyst that extracts Functional Requirements (FR) and Non-Functional Requirements (NFR) from requirement documents.

Given a requirement, SRS, or PRD document, extract all FR and NFR items.

Each FR/NFR item MUST be a JSON object with these exact fields:
{
  "id": "<e.g. FR-01 or NFR-01>",
  "title": "<short descriptive title>",
  "description": "<detailed description of the requirement>",
  "priority": "<high|medium|low>"
}

Return ONLY a valid JSON object with this structure:
{
  "fr": [<list of functional requirement objects>],
  "nfr": [<list of non-functional requirement objects>]
}

Do not include markdown fences or any other text. Return ONLY valid JSON.
"""

TESTCASE_SYSTEM_PROMPT = """You are an expert QA engineer specialised in writing comprehensive test cases.

Given a requirement document along with extracted Functional Requirements (FR) and Non-Functional Requirements (NFR), generate thorough test cases that cover:
- Happy path / positive scenarios
- Negative / error scenarios
- Edge cases and boundary conditions
- Performance considerations where relevant
- Security considerations where relevant

Each test case MUST map to one or more FR/NFR items and MUST be returned as a JSON object with these exact fields:
{
  "id": "<unique id string>",
  "title": "<short descriptive title>",
  "description": "<what the test verifies>",
  "preconditions": "<any setup required before the test>",
  "steps": ["<step 1>", "<step 2>", ...],
  "expected_result": "<what should happen>",
  "priority": "<high|medium|low>",
  "category": "<category e.g. functional/security/performance/usability>",
  "fr_nfr_ref": ["<the FR/NFR id this test case covers, e.g. FR-01>"]
}

Return ONLY a valid JSON array of test case objects. Do not include markdown fences or any other text. Return ONLY valid JSON.
"""

VALIDATION_SYSTEM_PROMPT = """You are an expert QA review engineer.

Given the original requirement, the extracted FR/NFR list, and a set of generated test cases, evaluate how well the test cases cover the requirements.

Return ONLY a valid JSON object with these exact fields:
{
  "coverage_score": <float between 0.0 and 1.0>,
  "missing_areas": ["<area not covered>", ...],
  "feedback": "<detailed textual feedback>",
  "is_sufficient": <true|false>
}

Do not include markdown fences or any other text. Return ONLY valid JSON.
"""


def _parse_json_response(text: str) -> list | dict:
    """Strip accidental markdown fences and parse JSON, tolerating common LLM quirks."""
    text = text.strip()

    # Remove markdown fences
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    # First try strict parsing
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fix common LLM JSON issues: invalid escape sequences
    fixed = re.sub(r'(?<!\\)\\(?!["\\/bfnrtu])', r'\\\\', text)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Last resort: extract JSON from text
    start_obj = text.find('{')
    start_arr = text.find('[')
    if start_obj >= 0 and (start_arr < 0 or start_obj < start_arr):
        end = text.rfind('}')
        if end > start_obj:
            try:
                return json.loads(text[start_obj:end + 1])
            except json.JSONDecodeError:
                pass
    elif start_arr >= 0:
        end = text.rfind(']')
        if end > start_arr:
            try:
                return json.loads(text[start_arr:end + 1])
            except json.JSONDecodeError:
                pass

    raise ValueError(f"Could not parse JSON from response: {text[:300]}")


async def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """Call OpenAI chat completions and return the response text."""
    response = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content


async def extract_fr_nfr(requirement: str) -> dict:
    """Extract FR/NFR from a requirement document."""
    prompt = (
        f"Extract all Functional Requirements (FR) and Non-Functional Requirements (NFR) "
        f"from the following requirement document.\n\n"
        f"REQUIREMENT:\n{requirement}"
    )

    logger.info("Starting FR/NFR extraction...")
    response_text = await _call_llm(FR_NFR_SYSTEM_PROMPT, prompt)
    logger.info(f"FR/NFR extraction response received ({len(response_text)} chars)")

    result = _parse_json_response(response_text)
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object with 'fr' and 'nfr' keys")
    if "fr" not in result or "nfr" not in result:
        raise ValueError("Response must have 'fr' and 'nfr' keys")

    logger.info(f"Extracted {len(result['fr'])} FR and {len(result['nfr'])} NFR items")
    return result


async def generate_testcases(requirement: str, fr_nfr: dict) -> list[dict]:
    """Generate test cases from a requirement and its FR/NFR list."""
    fr_nfr_str = json.dumps(fr_nfr, indent=2, ensure_ascii=False)
    prompt = (
        f"Generate comprehensive test cases for the following requirement. "
        f"Each test case must reference the specific FR or NFR id it covers using the 'fr_nfr_ref' field.\n\n"
        f"REQUIREMENT:\n{requirement}\n\n"
        f"FR/NFR LIST:\n{fr_nfr_str}"
    )

    logger.info("Starting test case generation...")
    response_text = await _call_llm(TESTCASE_SYSTEM_PROMPT, prompt)
    logger.info(f"Test case generation response received ({len(response_text)} chars)")

    result = _parse_json_response(response_text)
    if not isinstance(result, list):
        raise ValueError("Expected a JSON array of test cases")

    # Ensure each test case has an id and fr_nfr_ref is a list
    for tc in result:
        if "id" not in tc or not tc["id"]:
            tc["id"] = str(uuid.uuid4())
        # Normalize fr_nfr_ref to always be a list
        ref = tc.get("fr_nfr_ref", [])
        if isinstance(ref, str):
            tc["fr_nfr_ref"] = [ref]

    logger.info(f"Generated {len(result)} test cases")
    return result


async def validate_testcases(requirement: str, fr_nfr: dict, testcases: list[dict]) -> dict:
    """Validate test case coverage against requirements."""
    fr_nfr_str = json.dumps(fr_nfr, indent=2, ensure_ascii=False)
    testcases_str = json.dumps(testcases, indent=2, ensure_ascii=False)
    prompt = (
        f"Evaluate the following test cases against the requirement and FR/NFR list below.\n\n"
        f"REQUIREMENT:\n{requirement}\n\n"
        f"FR/NFR LIST:\n{fr_nfr_str}\n\n"
        f"TEST CASES:\n{testcases_str}"
    )

    logger.info("Starting validation...")
    response_text = await _call_llm(VALIDATION_SYSTEM_PROMPT, prompt)
    logger.info(f"Validation response received ({len(response_text)} chars)")

    result = _parse_json_response(response_text)
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object with validation results")

    logger.info(f"Validation complete: coverage={result.get('coverage_score')}, sufficient={result.get('is_sufficient')}")
    return result
