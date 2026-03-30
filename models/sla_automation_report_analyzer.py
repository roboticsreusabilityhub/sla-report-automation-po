from collections import Counter
from typing import Dict, List, Optional
import json
import re
from json_repair import repair_json
from models.IssueCauser import CauserCategory, ChunkIssueCauserResponse, IssueCauser
from models.Message import SystemMessage, UserMessage
from models.OpenAIChatCompletion import OpenAIChatCompletion
class SLAAutomationReportAnalyzer:
    ticket_path:str
    chat_completion_model:OpenAIChatCompletion

    system_message_content="""You are an enterprise AI validation assistant for Vodafone’s “Automation of SLA Reports Validation” in the SLM domain.
Your job: validate and (if needed) correct four fields per ticket using B-Log (technical logs, assignment answers, major outage docs, customer contacts) and T-Log (pending times). Fields:
1) Solution Time (“Störungsende”)
2) Total Pending Times (“Summe Auszeiten”)
3) Causer (“Verursacher”)
4) Solution Description (“Lösungsbeschreibung”)

General rules:
- Follow strict priority rules for each field (as below).
- Working hours: Mon–Fri 08:00–18:00 local; “Kontaktpause” is NOT pending time.
- Exclude red-marked pending intervals from totals (list under ignored).
- Pending intervals must not exceed Solution Time; merge overlaps with the same reason.
- Output strictly in JSON per each function’s schema. No free text outside JSON.
"""
    system_message=SystemMessage(content=system_message_content)

    def __init__(self,api_key,chunks:Optional[List[str]],model_name="gpt-4.1"):

   
        self.chunks=chunks
  
        self.chat_completion_model=OpenAIChatCompletion(api_key=api_key,system_message=self.system_message,default_model=model_name)
        pass


    def get_customer_name_via_prompt(self) -> Optional[dict]:
        """
        Loop over chunks; on first confident extraction of customer person/org, break and return.
        If nothing confident is found, return the best candidate (highest confidence) if any;
        otherwise return None.

        Returns:
            dict | None:
                {
                "customerPersonName": "First Last" | None,
                "customerOrganizationName": "Company" | None,
                "confidence_score": float (0.0-1.0),
                "evidenceLogs": [str, ...]  # up to 5 entries
                }
        """
        if not self.chunks:
            return None



        # Keep track of the best candidate across chunks in case we never hit a strong early exit
        best_candidate = None
        best_conf = -1.0

        for i, chunk in enumerate(self.chunks):
            chunk_text = str(chunk)

            message_content = f"""You are an information extraction assistant.

    TASK:
    Extract the CUSTOMER PERSON NAME and CUSTOMER ORGANIZATION from the following Vodafone ticket logs.

    HOW TO FIND THE CUSTOMER PERSON NAME AND COMPANY (FOLLOW THIS ORDER)
    You will find the anonmyzed label of the customer name beside "Kontaktname:" like this:
    e.g  "Kontaktname:"          [Person1]

    OUTPUT RULES:
    - Provide ONLY one MINIFIED JSON line with this exact schema:
    {{"customerPersonName":<string or null anonmyzed>,
 
    "confidence_score":<0.0-1.0>,
    "evidenceLogs":[<2-5 short English snippets quoting or paraphrasing the lines used>]}}

    CHUNK_INDEX: {i}
    CHUNK_TEXT:
    \"\"\"{chunk_text}\"\"\""""

            user_message = UserMessage(content=message_content)
            response_text = self.chat_completion_model.get_completion(
                user_message, without_history=True
            )
            raw_text = str(response_text).strip()

            parsed_obj = None

            # 1) Strict JSON parse
            try:
                parsed_obj = json.loads(raw_text)
            except Exception:
                parsed_obj = None

            # 2) Try to repair if available
            if parsed_obj is None and repair_json is not None:
                try:
                    repaired = repair_json(raw_text)
                    parsed_obj = json.loads(repaired)
                except Exception:
                    parsed_obj = None

            # 3) Heuristic cleanup fallback
            if parsed_obj is None:
                try:
                    cleaned = self._heuristic_clean_json(raw_text)
                    parsed_obj = json.loads(cleaned)
                except Exception:
                    parsed_obj = None

            if not isinstance(parsed_obj, dict):
                continue

            # Normalize fields
            person = self._norm_person(parsed_obj.get("customerPersonName"))
            org = self._norm_org(parsed_obj.get("customerOrganizationName"))
            try:
                conf = float(parsed_obj.get("confidence_score", 0.5))
            except Exception:
                conf = 0.5
            ev = parsed_obj.get("evidenceLogs")
            if not isinstance(ev, list):
                ev = []
            ev = ev[:5]

            # Update best-candidate tracker
            # Score preference: any non-null field is helpful; higher conf wins
            non_null_fields = int(person is not None) + int(org is not None)
            # heuristic: prioritize more fields + higher confidence
            score = (non_null_fields, conf)

            if non_null_fields > 0 and conf > best_conf:
                best_candidate = {
                    "customerPersonName": person,
                    "customerOrganizationName": org,
                    "confidence_score": conf,
                    "evidenceLogs": ev
                }
                best_conf = conf

            # Early exit condition:
            # If we found at least one of person/org with reasonable confidence, break.
            # You can tune the threshold; 0.6 is a good default to avoid weak early exits.
            if (person or org) and conf >= 0.6:
                return {
                    "customerPersonName": person,
                    "customerOrganizationName": org,
                    "confidence_score": conf,
                    "evidenceLogs": ev
                }

        # Fallback: return best candidate if any, else None
        return best_candidate

    def get_issue_causer(self) -> IssueCauser:
        """
        For each chunk in self.chunks, identify the causer of the issue.

        Returns:
            IssueCauserResponse (Pydantic): Aggregated final decision with per-chunk details.

        Behavior:
            - Uses strict JSON parsing first; if it fails, attempts json_repair (if available),
            then a heuristic cleanup as a final fallback.
            - Preserves anonymized labels exactly as they appear.
            - Majority voting across chunks for finalCauserCategory.
            - If a tie or no votes, tries to use the last chunk; otherwise defaults to "nicht nachvollziehbar".
            - finalCauserEntity is inferred from the last chunk that matches the final category if available,
            otherwise from any earlier chunk with a matching category.
        """
        from collections import Counter

        causer_results: List[ChunkIssueCauserResponse] = []
        voting_map: Counter = Counter()

        for i, chunk in enumerate(self.chunks):
            message_content = f"""You are an information extraction assistant.

    GOAL:
    Identify who CAUSED the issue described in the CHUNK_TEXT (German).

    Important:
    - All entities are anonymized (e.g., [Organization1], [Person1], [Site3]). You MUST preserve anonymized labels EXACTLY as they appear.
    - Do NOT de-anonymize, rename, or generalize anonymized tokens. Use them verbatim in your evidence and exact logs.

    Definition of "causer":
    - The "causer" is the party whose action, inaction, mistake, or device is responsible for the problem.
    - Do NOT invent evidence. Base conclusions ONLY on the provided logs.

    Allowed causer categories (German):
    - "Kunde"  → customer-side problem (home wiring, customer hardware/CPE, local misconfiguration, user action)
    - "Organisation" → network-side or provider-side problem (access/core network faults, outages, maintenance, backbone, node split, NE2/NE3, congestion, outside plant)
    - "nicht nachvollziehbar" → no error identified, issue disappeared, or insufficient evidence

    Determination rules:
    - If network-side faults/outages/Auslastung/Node Split/NE2–NE3 → causerCategory = "Organisation".
    - If home wiring, customer device, CPE misconfiguration, local environment → causerCategory = "Kunde".
    - If logs are inconclusive or issue vanished during troubleshooting → causerCategory = "nicht nachvollziehbar".

    Special rule for the last chunk:
    - LAST_CHUNK = {i == len(self.chunks)-1}
    - If this is the last chunk, you may infer the causer using:
        • explicit statements in this chunk, OR
        • references to a causer mentioned in earlier chunks.
    - If still unclear, set causerCategory = "nicht nachvollziehbar" and confidence_score low.

    Output format:
    - Output ONLY a single line of MINIFIED valid JSON. No Markdown, no code fences, no extra text.
    - Use this exact schema and keys (DE values for causerCategory):
    {{
    "causerCategory": "<Kunde|Organisation|nicht nachvollziehbar>",
    "causerEntity": "<exact anonymized token like [OrganizationN],[PersonN],etc>",
    "causerResultFoundInCurrentChunk": "<boolean>",
    "customerSideFault": "<boolean>",
    "organizationSideFault": "<boolean>",
    "noErrorIdentified": "<boolean>",
    "confidence_score": "<0.0-1.0>",
    "evidenceLogs": "<Translate the specific supporting log snippets to English. Keep anonymized labels EXACT>",
    "exactLogs": "<Quote the exact original log lines verbatim (German), including anonymized tokens. it should be a list of logs (List[str])>"
    }}

    Consistency constraints:
    - Exactly one of customerSideFault / organizationSideFault / noErrorIdentified must be true; the other two must be false.
    - causerCategory must match those booleans (Kunde ↔ customerSideFault; Organisation ↔ organizationSideFault; nicht nachvollziehbar ↔ noErrorIdentified).
    - If causerResultFoundInCurrentChunk is false, still provide your best category if LAST_CHUNK is true; otherwise set confidence_score low.

    NOTE:
    - The correct anonymized  network organization typically appears near lines containing "initiiert durch:" in technician or system logs.
    The field "causerEntity" must contain the EXACT anonymized entity responsible for causing the issue. 
    - If the causerCategory is "Kunde", then causerEntity MUST be the anonymized customer token (starting with "Person", e.g., "[Person4]"). 
    - If the causerCategory is "Organisation", then causerEntity MUST be the anonymized network organization token (starting with "Organization", e.g., "[Organization7]").
    - If the causerCategory is "nicht nachvollziehbar", then causerEntity MUST be null. 

    NOTE (CRITICAL):
    1. How to determine the network organization causerEntity:
    - When causerCategory = "Organisation", the causerEntity MUST be taken EXCLUSIVELY from the SAME line where the text says:
            "initiiert durch:"
    - The anonymized Vodafone network organization will ALWAYS appear on that exact line.
        Example before anonymization:
            initiiert durch:                   Vodafone
        After anonymization:
            initiiert durch:                   [Organization7]

    - The model MUST extract EXACTLY the anonymized token appearing on that same line (e.g., "[Organization7]").
    - The model MUST NOT select ANY other organization token appearing elsewhere in the 

    You MUST NOT invent or modify anonymized tokens and MUST ONLY use tokens that already appear in the provided CHUNK_TEXT.

    CHUNK_INDEX: {i}
    TOTAL_CHUNKS: {len(self.chunks)}

    CHUNK_TEXT (German):
    \"\"\"{str(chunk)}\"\"\""""

            # Get completion
            user_message = UserMessage(content=message_content)
            response_text = self.chat_completion_model.get_completion(
                user_message, without_history=True
            )
            raw_text = str(response_text).strip()

            parsed_obj = None

            # 1) Strict parse
            try:
                parsed_obj = json.loads(raw_text)
            except Exception:
                parsed_obj = None

            # 2) Repair via json_repair (if available)
            if parsed_obj is None and repair_json is not None:
                try:
                    repaired = repair_json(raw_text)
                    parsed_obj = json.loads(repaired)
                except Exception:
                    parsed_obj = None

            # 3) Heuristic cleanup
            if parsed_obj is None:
                try:
                    cleaned = self._heuristic_clean_json(raw_text)
                    parsed_obj = json.loads(cleaned)
                except Exception:
                    parsed_obj = None

            # Build chunk result
            if isinstance(parsed_obj, dict):
                # Normalize / coerce expected keys
                causer_category = parsed_obj.get("causerCategory")
                try:
                    # Construct pydantic model (will validate ranges/shape)
                    chunk_result = ChunkIssueCauserResponse(
                        chunk_index=i,
                        causerCategory=causer_category,
                        causerEntity=parsed_obj.get("causerEntity"),
                        causerResultFoundInCurrentChunk=parsed_obj.get("causerResultFoundInCurrentChunk"),
                        customerSideFault=parsed_obj.get("customerSideFault"),
                        organizationSideFault=parsed_obj.get("organizationSideFault"),
                        noErrorIdentified=parsed_obj.get("noErrorIdentified"),
                        confidence_score=parsed_obj.get("confidence_score"),
                        evidenceLogs=parsed_obj.get("evidenceLogs"),
                        exactLogs=parsed_obj.get("exactLogs"),
                        raw=raw_text,
                        parsed=parsed_obj
                    )
                except Exception as e:
                    print(e)

                    # If pydantic fails due to invalid types, fallback to minimal
                    chunk_result = ChunkIssueCauserResponse(
                        chunk_index=i,
                        causerCategory=causer_category,
                        raw=raw_text,
                        parsed=parsed_obj
                    )
            else:
                # Unparseable → mark as unknown with low confidence
                chunk_result = ChunkIssueCauserResponse(
                    chunk_index=i,
                    causerCategory="nicht nachvollziehbar",
                    noErrorIdentified=True,
                    customerSideFault=False,
                    organizationSideFault=False,
                    confidence_score=0.0,
                    raw=raw_text,
                    parsed=None,
                    evidenceLogs=[],
                    exactLogs=[]
                )

            # Tally votes if we have a category
            if chunk_result.causerCategory in ("Kunde", "Organisation", "nicht nachvollziehbar"):
                voting_map.update([chunk_result.causerCategory])  # counts None won't occur here

            causer_results.append(chunk_result)
            print(chunk_result)

        # -----------------------------
        # Decide final category (majority; break ties preferring last chunk)
        # -----------------------------
        final_category: CauserCategory = "nicht nachvollziehbar"
        vote_tally: Dict[CauserCategory, int] = {
            "Kunde": 0,
            "Organisation": 0,
            "nicht nachvollziehbar": 0
        }
        vote_tally.update({k: int(v) for k, v in voting_map.items()})

        if voting_map:
            most_common = voting_map.most_common()
            if len(most_common) == 1:
                final_category = most_common[0][0]
            else:
                # Check for tie
                top_count = most_common[0][1]
                top_cats = [cat for cat, cnt in most_common if cnt == top_count]
                if len(top_cats) == 1:
                    final_category = top_cats[0]
                else:
                    # Tie → prefer last chunk's category if present
                    last_chunk_cat = causer_results[-1].causerCategory if causer_results else None
                    if last_chunk_cat in top_cats:
                        final_category = last_chunk_cat  # type: ignore
                    else:
                        final_category = "nicht nachvollziehbar"
        else:
            # No votes → default
            final_category = "nicht nachvollziehbar"

        # -----------------------------
        # Decide final entity consistent with final category
        # Prefer: last chunk with matching category & non-empty entity
        # Fallback: first chunk with matching category & non-empty entity
        # If 'nicht nachvollziehbar' → None
        # -----------------------------
        final_entity: Optional[str] = None
        if final_category != "nicht nachvollziehbar":
            # last to first search
            for chk in reversed(causer_results):
                if chk.causerCategory == final_category and chk.causerEntity:
                    final_entity = chk.causerEntity
                    break
            if final_entity is None:
                for chk in causer_results:
                    if chk.causerCategory == final_category and chk.causerEntity:
                        final_entity = chk.causerEntity
                        break

        # Build the pydantic response
        response = IssueCauser(
            finalCauserCategory=final_category,
            finalCauserEntity=final_entity,
            voteTally=vote_tally,
            perChunk=causer_results,
            evidence=parsed_obj.get("evidenceLogs"),
            exactLogs=parsed_obj.get("exactLogs")
        )

        return response
  

      # Heuristic cleanup as last resort
    def _heuristic_clean_json(text: str) -> str:
        cleaned = text.strip()

        # Remove code fences if present
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = re.sub(r"^json", "", cleaned, flags=re.IGNORECASE).strip()

        # If there are multiple braces, take the first full JSON object
        first_brace = cleaned.find("{")
        last_brace = cleaned.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            cleaned = cleaned[first_brace:last_brace + 1]

        # Remove trailing commas before } or ]
        cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)

        # Replace single quotes with double quotes when they look like string delimiters
        # (cheap heuristic; avoids messing with apostrophes inside words by limiting to JSON-ish contexts)
        cleaned = re.sub(r"(?<!\\)'", '"', cleaned)

        return cleaned
    def _norm_person(self,name: Optional[str]) -> Optional[str]:
        if not name or not isinstance(name, str):
            return None
        s = name.strip()
        # Remove honorifics
        s = re.sub(r"\b(Herr|Frau|Mr\.?|Mrs\.?|Ms\.?)\b", "", s, flags=re.IGNORECASE).strip()
        # Collapse spaces
        s = re.sub(r"\s{2,}", " ", s)
        return s or None

    def _norm_org(self,name: Optional[str]) -> Optional[str]:
        if not name or not isinstance(name, str):
            return None
        s = name.strip()
        s = re.sub(r"\s{2,}", " ", s)
        return s or None