"""The domain ring: the single hand-written source of the model.

Cross-cutting terminological conventions — the words the model refuses to use,
so they cannot drift into concepts:

- "source" is reserved for live speech and never names a model concept; the
  configured place documents come from is an AcquisitionChannel.
- "candidate" is a stage of a Document's lifecycle, not a concept of its own.
- "corpus" is a state predicate — all ACTIVE documents of the registry — not a
  stored thing: no id, no configuration, no lifecycle.
"""
