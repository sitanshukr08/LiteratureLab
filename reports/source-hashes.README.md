# Source integrity manifest

source-hashes.json records SHA-256 of UTF-8 source bytes after normalizing CRLF to LF. Git archives normalize text line endings, so compare normalized bytes rather than platform-specific working-tree newlines. The manifest covers application, browser, scripts and tests; it excludes secrets and runtime data.
