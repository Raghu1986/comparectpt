DEFAULT_EXTRACTION_PROMPT = """You are tasked with extracting specific information from an insurance document.
All occurrences of the required fields mentioned below should be extracted along with the correct page number.

The required fields are:

1. Policy Number
2. Policy Period
3. Insurance Company
4. Named Insured and Mailing Address

---------------------------
Step 1: Identification
---------------------------

Identify ALL occurrences of the following:

1. Policy Number:
   - A unique identifier linked with any labels such as:
     POLICY NUMBER / POLICY NO / POLICY # / CERTIFICATE NO / COVER NOTE NUMBER / RENEWAL NUMBER
   - May contain alphanumeric characters, spaces, hyphens.
   - Do NOT extract Document Number or File Number.
   - Each match must include the exact page number where it was found.

2. Policy Period:
   - Contains two components: FROM date and TO date.
   - Valid formats:
        FROM: MM/DD/YYYY
        TO:   MM/DD/YYYY
        OR phrases such as:
            \"Continuous Until Cancelled\",
            \"Until Cancelled\",
            \"Ongoing\".
   - Extract all occurrences.
   - Each occurrence must include the exact page number where it was found.

3. Insurance Company:
   - Extract the issuing company name.
   - Usually found near \"Issuing Company\" label.
   - Extract all occurrences.
   - Each occurrence must include the exact page number where it was found.

4. Named Insured and Mailing Address:
   - Extract all occurrences of:
        - Named Insured
        - Mailing Address
   - Address should be a typical address containing street, city, state, ZIP.
   - Each occurrence must include the exact page number where it was found.

Use the supplied page markers exactly as the source of truth for page numbers.
Return valid JSON only, with no markdown fences and no commentary, using this exact shape:
{
  \"policy_numbers\": [{\"value\": string, \"page\": int}],
  \"policy_periods\": [{\"from\": string | null, \"to\": string | null, \"page\": int}],
  \"insurance_companies\": [{\"value\": string, \"page\": int}],
  \"named_insured_and_mailing_addresses\": [{\"named_insured\": string | null, \"mailing_address\": string | null, \"page\": int}],
  \"notes\": [string]
}
If a field is absent, return an empty array for that field."""

DEFAULT_MERGE_PROMPT = """You are merging extraction results from a current-term insurance document and a prior-term insurance document.
Compare both extractions and return valid JSON only, with no markdown fences and no commentary, using this exact shape:
{
  \"current_term\": {
    \"policy_numbers\": [{\"value\": string, \"page\": int}],
    \"policy_periods\": [{\"from\": string | null, \"to\": string | null, \"page\": int}],
    \"insurance_companies\": [{\"value\": string, \"page\": int}],
    \"named_insured_and_mailing_addresses\": [{\"named_insured\": string | null, \"mailing_address\": string | null, \"page\": int}],
    \"notes\": [string]
  },
  \"prior_term\": {
    \"policy_numbers\": [{\"value\": string, \"page\": int}],
    \"policy_periods\": [{\"from\": string | null, \"to\": string | null, \"page\": int}],
    \"insurance_companies\": [{\"value\": string, \"page\": int}],
    \"named_insured_and_mailing_addresses\": [{\"named_insured\": string | null, \"mailing_address\": string | null, \"page\": int}],
    \"notes\": [string]
  },
  \"comparison_summary\": [string],
  \"field_level_changes\": [
    {
      \"field\": string,
      \"current_value\": string | null,
      \"prior_value\": string | null,
      \"current_page\": int | null,
      \"prior_page\": int | null,
      \"observation\": string | null,
      \"change_type\": \"added\" | \"removed\" | \"changed\" | \"unchanged\"
    }
  ]
}
Preserve all page numbers exactly as provided in the source extraction JSON.

For each item in `field_level_changes`, include `current_page` and `prior_page` whenever page numbers are available.
Also include an `observation` string summarizing the compared source content in a format such as:
`Current term content(s): <value> Prior term content(s): <value>`

Comparison rules:
- Compare string values case-insensitively unless case itself is materially meaningful.
- For insurance company names, treat formatting-only differences as unchanged.
- For insurance company names, treat a short form or alias as unchanged when it clearly refers to the same company as the full legal name.
- Only mark insurance company names as changed when the company is actually different, not when one document uses uppercase, punctuation differences, or a shortened version of the same name."""

PREMIUM_EXTRACTION_PROMPT_SAMPLE = """Identify only the renewal premium at the Line of Business (LOB) level.

A Line of Business includes (but is not limited to):
- Commercial Package (HUD)
- Commercial Package (Non-HUD)
- Commercial Property (HUD)
- Commercial Property (Non-HUD)
- Commercial Auto
- Cyber Liability
- Umbrella
- Vacant Property
- Any other top-level coverage category

A premium amount typically appears in formats such as:
$12,345 / $12,345.00 / 12345 (treated as $12,345.00 when no decimals appear).

-------------------------------------
Step 2: Extraction Rules
-------------------------------------
Extract ONLY the renewal premium at the LOB level.
Do NOT extract:
- Intermediate values
- Sub-coverage or component premiums (e.g., General Liability, Professional Liability)
- Zero amounts (e.g., $0.00 or $)

Each extracted value must be returned exactly as written and associated with:
- The page number
- The premium amount exactly as shown in the document

-------------------------------------
Step 3: Validation
-------------------------------------
Ensure every extracted premium:
- Contains a valid currency amount
- Is next to or below a LOB header or premium label
- Is not a rate (e.g., 0.361)
- Is not a deductible
- Is not a percentage
- Is not a limit or insured value (e.g., $15,784,423)

-------------------------------------
Step 4: Output Format
-------------------------------------
Output ONE JSON object per LOB premium found, using:

{"pagenumber": <int>, "Premium(TP1)": "$xxx.xx"}

Examples:
{"pagenumber": 12, "Premium(TP1)": "$56,818.00"}
{"pagenumber": 12, "Premium(TP1)": "$59,649.00"}

If no LOB premium values are found:
{"Premium(TP1)": "Not Found"}

-------------------------------------
Important:
-------------------------------------
- Preserve the exact currency formatting.
- Return one JSON object per premium.
- Do not add explanations or commentary."""

PREMIUM_MERGE_PROMPT = """You are merging premium extraction results from a current-term insurance document and a prior-term insurance document.
Compare both premium extraction outputs and return valid JSON only, with no markdown fences and no commentary, using this exact shape:
{
  "current_term": {
    "premiums": [{"line_of_business": string | null, "value": string, "page": int}]
  },
  "prior_term": {
    "premiums": [{"line_of_business": string | null, "value": string, "page": int}]
  },
  "comparison_summary": [string],
  "field_level_changes": [
    {
      "field": string,
      "current_value": string | null,
      "prior_value": string | null,
      "current_page": int | null,
      "prior_page": int | null,
      "observation": string | null,
      "change_type": "added" | "removed" | "changed" | "unchanged"
    }
  ]
}

Rules:
- Preserve all page numbers exactly as provided in the source extraction output.
- Match premiums by line_of_business when available.
- If a matching line of business exists on both sides with the same premium, mark it as unchanged.
- If a matching line of business exists on both sides with a different premium, mark it as changed.
- If a premium exists on only one side, mark it as added or removed.
- If line_of_business is missing, compare by premium position as a fallback.
- Use a field name like "Premium(TP1)" when there is a single premium value without a better business label.
- Include `current_page` and `prior_page` in every `field_level_changes` item whenever available.
- Include an `observation` string for every `field_level_changes` item, for example:
  `Current term content(s): $4,000.00 Prior term content(s): $4,000.00`
- Write comparison summaries in business language such as:
  "Premium TP1 remains unchanged at $4,000.00 on page 4"
  "Premium TP1 changed from $3,500.00 to $4,000.00"
  "Premium TP1 was added at $4,000.00 on page 4"."""


def get_insurance_prompts() -> dict[str, str]:
    return {
        "current_prompt": DEFAULT_EXTRACTION_PROMPT,
        "prior_prompt": DEFAULT_EXTRACTION_PROMPT,
        "merge_prompt": DEFAULT_MERGE_PROMPT,
        "premium_extraction_prompt_sample": PREMIUM_EXTRACTION_PROMPT_SAMPLE,
        "premium_merge_prompt": PREMIUM_MERGE_PROMPT,
    }
