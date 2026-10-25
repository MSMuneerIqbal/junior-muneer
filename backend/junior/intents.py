"""Conservative, local guard against spending tokens reading files in a save-only request."""
import re


def storage_only(text: str) -> bool:
    text = re.sub(r"\[file \d+:[^\]]*\]", "", text or "", flags=re.I).casefold()
    store = re.search(r"\b(save|upload|store|copy|place|put|keep)\b", text)
    if not store:
        return False
    if re.search(r"\b(just|only)\s+(save|upload|store|copy|place|put)\b|(?:don't|do not|without)\s+read", text):
        return True
    analysis = re.search(r"\b(read|summari[sz]e|explain|analy[sz]e|review|extract|transcribe|translate|answer)\b|\bwhat does .{0,25}say\b|\b(make|create|prepare|write)\b.{0,35}\b(notes|summary|report)\b", text)
    return analysis is None


def reading_refusal(context):
    if storage_only(getattr(context, "user_text", "")):
        return "NOT read: this is a save/upload-only request. Use place_document to store the actual file without reading or summarizing it."
    return None
