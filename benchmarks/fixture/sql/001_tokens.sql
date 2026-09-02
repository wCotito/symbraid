-- A deterministic schema fragment used by the benchmark fixture.
CREATE TABLE access_tokens (
    token_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    last_rotated_at TIMESTAMP NOT NULL
);

CREATE INDEX access_tokens_subject_idx ON access_tokens(subject_id);
