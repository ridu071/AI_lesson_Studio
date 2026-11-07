"""Provider-neutral access to language models.

QC code depends only on LLMClient and the errors below. Provider details
(HTTP calls, retries, response formats) stay inside one client module.
"""
