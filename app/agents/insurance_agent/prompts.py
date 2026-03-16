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
      \"change_type\": \"added\" | \"removed\" | \"changed\" | \"unchanged\"
    }
  ]
}
Preserve all page numbers exactly as provided in the source extraction JSON.

Comparison rules:
- Compare string values case-insensitively unless case itself is materially meaningful.
- For insurance company names, treat formatting-only differences as unchanged.
- For insurance company names, treat a short form or alias as unchanged when it clearly refers to the same company as the full legal name.
- Only mark insurance company names as changed when the company is actually different, not when one document uses uppercase, punctuation differences, or a shortened version of the same name."""
