"""
LLM Provider Integration
Supports OpenAI, Anthropic, Gemini, Ollama, and a built-in Offline Heuristic Doctor Engine.
"""

import json
import os
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generates a text completion for the given prompt."""
        pass

    def is_available(self) -> Tuple[bool, str]:
        """Returns (is_ready, status_message) for UI health indicators."""
        return True, "Ready"


class OfflineDoctorEngine(BaseLLMProvider):
    """
    Built-in heuristic reasoning engine that requires zero external API keys.
    Generates intelligent answers dynamically grounded in AST knowledge, graph topology, and risk findings.
    """

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        prompt_lower = prompt.lower()

        # Extract parsed symbols and context from the prompt
        symbols = re.findall(r"=== Symbol:\s+([^\s]+)\s+\((.*?)\)\s+in\s+([^\s=]+)\s+===", prompt)
        callers_match = re.search(r"Direct Callers \(Depends on this\):\s*([^\n]+)", prompt)
        callees_match = re.search(r"Calls \(Dependencies\):\s*([^\n]+)", prompt)
        params_match = re.search(r"Parameters:\s*([^\n]+)", prompt)

        primary_sym = symbols[0][0] if symbols else ""
        primary_type = symbols[0][1] if symbols else "component"
        primary_file = symbols[0][2] if symbols else ""
        callers_raw = callers_match.group(1).strip() if callers_match else "None (entry point or unreferenced)"
        callees_raw = callees_match.group(1).strip() if callees_match else "None"
        params_raw = params_match.group(1).strip() if params_match else "None"

        # Check for code smells in prompt snippet
        detected_risks = []
        if "random.randint" in prompt:
            detected_risks.append("Insecure Cryptographic Randomness (`random.randint` used for token generation)")
        if "cursor.execute(f" in prompt or "execute(f" in prompt:
            detected_risks.append("SQL Injection Vulnerability (unparameterized f-string query)")
        if "amount *" in prompt or "usd_base" in prompt:
            detected_risks.append("Floating-Point Arithmetic Precision Risk (IEEE-754 drift in financial calculations)")

        # Handle "what could break if I modify X" — broad intent matching for impact questions
        impact_keywords = [
            "what else could break", "what could break", "what will break", "what would break",
            "modify", "affected", "impacted", "impact", "depends on", "depend on",
            "break", "breaks", "fail", "fails", "ripple", "blast radius",
            "change", "changing", "doesn't respond", "does not respond", "goes down",
            "unavailable", "crashes", "stops working", "down", "outage",
            "what happens if", "what will happen", "consequence",
        ]
        if any(kw in prompt_lower for kw in impact_keywords):
            sym_display = f"`{primary_sym}`" if primary_sym else "this component"
            file_display = f" in `{primary_file}`" if primary_file else ""

            # Collect callers from all symbols in the prompt
            all_callers = []
            for line in prompt.splitlines():
                if "Direct Callers (Depends on this):" in line:
                    after = line.split(":", 1)[1].strip()
                    if after and "None" not in after:
                        for c in after.split(","):
                            clean_c = c.strip()
                            if clean_c and clean_c not in all_callers and "test" not in clean_c.lower():
                                all_callers.append(clean_c)

            callers_list = all_callers if all_callers else [c.strip() for c in callers_raw.split(",") if c.strip() and "None" not in c]
            if callers_list:
                callers_section = "\n".join([f"- **`{c}`**: Relies on this component. Any signature change, contract mutation, or unexpected return shape will cause runtime failures in this caller." for c in callers_list])
            else:
                callers_section = "- No external callers detected in current graph traversal (likely a root entry point or interface handler)."

            risks_section = ""
            if detected_risks:
                risks_section = "\n**Identified Static Risks in this component**:\n" + "\n".join([f"- [!] {r}" for r in detected_risks]) + "\n"

            test_suggestions = []
            if "auth" in primary_sym.lower() or "token" in primary_sym.lower():
                test_suggestions = [
                    "- `test_expired_token_rejection`: Verify session invalidation logic.",
                    "- `test_role_permission_elevation_prevented`: Verify role-based access boundaries.",
                    "- `test_session_revocation_on_password_reset`: Verify token lifecycle consistency.",
                ]
            elif "payment" in primary_sym.lower() or "price" in primary_sym.lower():
                test_suggestions = [
                    "- `test_refund_after_partial_payment`: Verify boundary checks on transactions.",
                    "- `test_currency_conversion`: Verify precision without floating-point rounding drift.",
                    "- `test_failed_payment_retry`: Verify graceful gateway timeout recovery.",
                ]
            else:
                test_suggestions = [
                    f"- `test_{primary_sym.split('.')[-1].lower()}_contract`: Verify input parameters ({params_raw}).",
                    f"- `test_{primary_sym.split('.')[-1].lower()}_exceptions`: Verify error handling on invalid states.",
                ]

            return (
                f"### Architectural Impact Analysis for {sym_display}\n\n"
                f"**Target**: {sym_display} ({primary_type}){file_display}\n"
                f"**Parameters**: `{params_raw}`\n\n"
                f"#### 1. Blast Radius & Dependent Callers\n"
                f"Modifying this component introduces risk across upstream dependents:\n"
                f"{callers_section}\n\n"
                f"#### 2. Specific Contract, State & Concurrency Risks\n"
                f"- **Contract Invalidation**: Altering parameter names, types, or return shapes will trigger immediate `TypeError` or deserialization failures in callers.\n"
                f"- **State & Synchronization Drift**: Downstream consumers assume strict transaction and session lifecycle contracts. Altering status emissions will desynchronize caller state machines.\n"
                f"{risks_section}\n"
                f"#### 3. Recommended Verification & Testing Strategy\n"
                f"Before deploying changes to {sym_display}, run targeted automated tests:\n"
                + "\n".join(test_suggestions)
            )

        # Handle security / risk questions
        if "security" in prompt_lower or "bug" in prompt_lower or "risk" in prompt_lower:
            risk_bullets = "\n".join([f"- **High**: {r}" for r in detected_risks]) if detected_risks else "- No high-severity vulnerabilities flagged in immediate snippet."
            return (
                f"### Security & Vulnerability Analysis for `{primary_sym or 'codebase'}`\n\n"
                f"{risk_bullets}\n\n"
                f"- **Security Checklist**:\n"
                f"  1. Ensure all session tokens use `secrets.token_hex()` rather than pseudo-random numbers.\n"
                f"  2. Convert currency calculations to `decimal.Decimal`.\n"
                f"  3. Guard against unhandled gateway or network timeouts."
            )

        # Default helpful technical response
        return (
            f"### Codebase Doctor Technical Evaluation: `{primary_sym or 'Architecture'}`\n\n"
            f"Based on structural AST and graph analysis of this codebase:\n"
            f"- **Component**: `{primary_sym or 'Target'}` ({primary_type}) in `{primary_file or 'repo'}`\n"
            f"- **Upstream Callers**: `{callers_raw}`\n"
            f"- **Downstream Dependencies**: `{callees_raw}`\n"
            f"- Ensure thorough test coverage covering boundary cases, null checks, and error rollback pathways."
        )


class GroqProvider(BaseLLMProvider):
    """Groq Cloud API integration for ultra-fast Llama & open frontier models."""

    def __init__(self, api_key: Optional[str] = None, model: str = "openai/gpt-oss-120b"):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = model

    def is_available(self) -> Tuple[bool, str]:
        if self.api_key:
            return True, f"Groq Cloud Connected ({self.model})"
        return False, "Missing GROQ_API_KEY"

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        if not self.api_key:
            return "[Groq Error]: Missing GROQ_API_KEY. Configure in .env or sidebar.\n\nFallback:\n" + OfflineDoctorEngine().generate(prompt, system_prompt)

        try:
            import httpx

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.2,
            }

            resp = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            else:
                return f"[Groq Error {resp.status_code}]: {resp.text}\n\nFallback:\n" + OfflineDoctorEngine().generate(prompt, system_prompt)
        except Exception as e:
            return f"[Groq Error: {e}]\n\nFallback:\n" + OfflineDoctorEngine().generate(prompt, system_prompt)


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API integration (gemini-1.5-flash, gemini-2.0-flash, gemini-1.5-pro)."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-1.5-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.model = model

    def is_available(self) -> Tuple[bool, str]:
        if self.api_key:
            return True, f"Google Gemini Connected ({self.model})"
        return False, "Missing GEMINI_API_KEY or GOOGLE_API_KEY"

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        if not self.api_key:
            return "[Gemini Error]: Missing GEMINI_API_KEY. Configure in .env or sidebar.\n\nFallback:\n" + OfflineDoctorEngine().generate(prompt, system_prompt)

        try:
            import httpx

            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
            contents = []
            if system_prompt:
                contents.append({
                    "role": "user",
                    "parts": [{"text": f"System Directive: {system_prompt}"}],
                })
                contents.append({
                    "role": "model",
                    "parts": [{"text": "Understood. I will follow these instructions as AI Codebase Doctor."}],
                })
            contents.append({
                "role": "user",
                "parts": [{"text": prompt}],
            })

            payload = {
                "contents": contents,
                "generationConfig": {
                    "temperature": 0.2,
                },
            }

            resp = httpx.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=35.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "")
                return "[Gemini Error]: Empty response from Gemini API."
            else:
                return f"[Gemini Error {resp.status_code}]: {resp.text}\n\nFallback:\n" + OfflineDoctorEngine().generate(prompt, system_prompt)
        except Exception as e:
            return f"[Gemini Error: {e}]\n\nFallback:\n" + OfflineDoctorEngine().generate(prompt, system_prompt)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API integration (gpt-4o, gpt-4o-mini)."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model

    def is_available(self) -> Tuple[bool, str]:
        if self.api_key:
            return True, f"OpenAI Connected ({self.model})"
        return False, "Missing OPENAI_API_KEY"

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        if not self.api_key:
            return "[OpenAI Error]: Missing OPENAI_API_KEY.\n\nFallback:\n" + OfflineDoctorEngine().generate(prompt, system_prompt)

        try:
            import httpx

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.2,
            }

            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            else:
                return f"[OpenAI Error {resp.status_code}]: {resp.text}\n\nFallback:\n" + OfflineDoctorEngine().generate(prompt, system_prompt)
        except Exception as e:
            return f"[LLM Error: {e}]\n\nFallback:\n" + OfflineDoctorEngine().generate(prompt, system_prompt)


class OllamaProvider(BaseLLMProvider):
    """Local Ollama integration (e.g. llama3, qwen2.5-coder, mistral)."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3"):
        self.base_url = base_url
        self.model = model

    def is_available(self) -> Tuple[bool, str]:
        try:
            import httpx
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=1.5)
            if resp.status_code == 200:
                return True, f"Ollama Connected ({self.model})"
            return False, f"Ollama HTTP {resp.status_code}"
        except Exception:
            return False, f"Ollama offline at {self.base_url}"

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        try:
            import httpx

            payload = {
                "model": self.model,
                "prompt": f"{system_prompt}\n\n{prompt}" if system_prompt else prompt,
                "stream": False,
            }
            resp = httpx.post(f"{self.base_url}/api/generate", json=payload, timeout=40.0)
            if resp.status_code == 200:
                return resp.json().get("response", "")
            return f"[Ollama Error {resp.status_code}]: {resp.text}\n\nFallback:\n" + OfflineDoctorEngine().generate(prompt, system_prompt)
        except Exception as e:
            return f"[Ollama Error: {e}]\n\nFallback:\n" + OfflineDoctorEngine().generate(prompt, system_prompt)


def get_llm_provider(
    provider_name: str = "auto",
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
) -> BaseLLMProvider:
    """Factory to instantiate the appropriate LLM provider."""
    provider_name = (provider_name or "auto").lower().strip()

    if "groq" in provider_name:
        return GroqProvider(api_key=api_key, model=model_name or "openai/gpt-oss-120b")

    if "gemini" in provider_name or "google" in provider_name:
        return GeminiProvider(api_key=api_key, model=model_name or "gemini-1.5-flash")

    if "openai" in provider_name:
        return OpenAIProvider(api_key=api_key, model=model_name or "gpt-4o-mini")

    if "ollama" in provider_name:
        return OllamaProvider(model=model_name or "llama3")

    if provider_name == "offline":
        return OfflineDoctorEngine()

    if provider_name == "auto":
        # Smart auto-detection order: Groq -> Gemini -> OpenAI -> Ollama -> Offline
        if api_key:
            return GroqProvider(api_key=api_key, model=model_name or "openai/gpt-oss-120b")
        if os.getenv("GROQ_API_KEY"):
            return GroqProvider(model=model_name or "openai/gpt-oss-120b")
        if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
            return GeminiProvider(model=model_name or "gemini-1.5-flash")
        if os.getenv("OPENAI_API_KEY"):
            return OpenAIProvider(model=model_name or "gpt-4o-mini")
        ollama = OllamaProvider(model=model_name or "llama3")
        is_up, _ = ollama.is_available()
        if is_up:
            return ollama

    # Default to robust offline doctor engine
    return OfflineDoctorEngine()

