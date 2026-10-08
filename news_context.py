"""Keep bounded actual source sentences from both lead and latest tail."""
import re


def source_context(text, limit=3800):
    if len(text) <= limit:
        return text
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    head, tail = [], []
    head_size = tail_size = 0
    for sentence in sentences:
        if head_size + len(sentence) + 1 > limit // 2:
            break
        head.append(sentence)
        head_size += len(sentence) + 1
    for sentence in reversed(sentences[len(head):]):
        if tail_size + len(sentence) + 1 > limit // 2:
            break
        tail.insert(0, sentence)
        tail_size += len(sentence) + 1
    if not head or not tail:
        # A source with no usable sentence boundaries must be extracted correctly,
        # not silently truncated into an incomplete claim.
        raise ValueError('Source has no bounded complete lead and update sentences')
    return '\n'.join(['KAYNAĞIN BAŞLANGICI:', *head, 'KAYNAĞIN SON BÖLÜMÜ:', *tail])
