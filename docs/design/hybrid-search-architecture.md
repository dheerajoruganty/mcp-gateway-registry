# Hybrid Search Architecture

This document describes the hybrid search design for MCP servers and A2A agents in the registry.

## Overview

The registry implements hybrid search that combines semantic (vector) search with lexical (keyword) matching. This approach provides both conceptual understanding of queries and precise matching when users reference entities by name.

## Architecture Diagram

```
                              +-------------------+
                              |   Search Query    |
                              |  "context7 docs"  |
                              +--------+----------+
                                       |
                     +-----------------+-----------------+
                     |                                   |
                     v                                   v
           +------------------+               +-------------------+
           |  Query Embedding |               |  Query Tokenizer  |
           |  (Vector Model)  |               |  (Keyword Extract)|
           +--------+---------+               +---------+---------+
                    |                                   |
                    | [0.12, -0.34, ...]               | ["context7", "docs"]
                    |                                   |
                    v                                   v
           +------------------+               +-------------------+
           |  Vector Search   |               |  Keyword Match    |
           |  (Cosine Sim)    |               |  (Regex on path,  |
           |                  |               |   name, desc,     |
           |                  |               |   tags, tools)    |
           +--------+---------+               +---------+---------+
                    |                                   |
                    | semantic_score                    | text_boost
                    |                                   |
                    +----------------+------------------+
                                     |
                                     v
                          +---------------------+
                          |  Score Combination  |
                          |  relevance_score =  |
                          |  semantic + boost   |
                          +----------+----------+
                                     |
                                     v
                          +---------------------+
                          |  Result Grouping    |
                          |  - servers (top 3)  |
                          |  - agents (top 3)   |
                          +----------+----------+
                                     |
                                     v
                          +---------------------+
                          |  Tool Extraction    |
                          |  Extract matching   |
                          |  tools from servers |
                          |  -> tools[] (top 3) |
                          +---------------------+
```

## Search Flow

### 1. Query Processing

When a search query arrives:

1. **Embedding Generation**: Query is converted to a vector embedding using the configured model (Amazon Bedrock, OpenAI, or local sentence-transformers)

2. **Tokenization**: Query is split into meaningful keywords
   - Non-word characters are removed
   - Stopwords filtered (a, the, is, are, etc.)
   - Tokens shorter than 3 characters removed

### 2. Dual Search Strategy

**Vector Search (Semantic)**
- Uses HNSW index on DocumentDB (production) or application-level cosine similarity on MongoDB CE
- Finds conceptually similar content even with different wording
- Returns results sorted by cosine similarity

**Keyword Search (Lexical)**
- Regex matching on path, name, description, tags, and tool names/descriptions
- Catches explicit references that semantic search might miss
- Runs as separate query due to DocumentDB limitations (no `$unionWith` support)

### 3. Score Combination

The final relevance score combines both approaches:

```
relevance_score = normalized_vector_score + (text_boost * 0.1)
```

Text boost values:
| Match Location | Boost Value |
|----------------|-------------|
| Path           | +5.0        |
| Name           | +3.0        |
| Description    | +2.0        |
| Tags           | +1.5        |
| Tool (each)    | +1.0        |

### 4. Result Structure

Search returns grouped results:

```json
{
  "servers": [
    {
      "path": "/context7",
      "server_name": "Context7 MCP Server",
      "relevance_score": 1.0,
      "matching_tools": [
        {"tool_name": "query-docs", "description": "..."}
      ]
    }
  ],
  "tools": [
    {
      "server_path": "/context7",
      "tool_name": "query-docs",
      "inputSchema": {...}
    }
  ],
  "agents": [...]
}
```

## Entity Types

### MCP Servers

**What's included in the embedding:**
- Server name
- Server description
- Tags (prefixed with "Tags: ")
- Tool names (each tool's name)
- Tool descriptions (each tool's description)

**What's NOT included in the embedding:**
- Tool inputSchema (JSON schema is stored but not embedded)
- Server path
- Server metadata

**Stored document fields:**
- `path`, `name`, `description`, `tags`, `is_enabled`
- `tools[]` array with `name`, `description`, `inputSchema` per tool
- `embedding` vector
- `metadata` (full server info for reference)

### A2A Agents

**What's included in the embedding:**
- Agent name
- Agent description
- Tags (prefixed with "Tags: ")
- Capabilities (prefixed with "Capabilities: ")
- Skill names (each skill's name)
- Skill descriptions (each skill's description)

**What's NOT included in the embedding:**
- Agent path
- Agent card metadata (stored but not embedded)
- Skill IDs, tags, and examples

**Stored document fields:**
- `path`, `name`, `description`, `tags`, `is_enabled`
- `capabilities[]` array
- `embedding` vector
- `metadata` (full agent card for reference)

### Tools

- Not indexed separately - extracted from parent server documents
- When a server matches, its tools are checked for keyword matches
- Top-level `tools[]` array contains full schema (inputSchema)
- `matching_tools` in server results is a lightweight reference (no schema)

## Backend Implementations

### DocumentDB (Production)
- Native HNSW vector index with `$search` aggregation pipeline
- Keyword query runs separately and merges results (no `$unionWith` support)
- Text boost calculated in aggregation pipeline using `$regexMatch`

### MongoDB CE (Development/Local)
- No native vector search support (`$vectorSearch` not available)
- Falls back to application-level search (in Python backend, not the calling agent):
  1. Fetch all documents with embeddings from collection
  2. Calculate cosine similarity in Python code
  3. Apply keyword matching and text boost in application
  4. Sort and limit results
- Same API contract as DocumentDB implementation

## Lexical Fallback Mode

When the embedding model is unavailable (misconfigured, network issues, API key expired, model not found), the search system automatically degrades to **lexical-only mode** instead of failing entirely.

### How It Works

1. **Detection**: On the first search request, if the embedding model fails to generate a query vector, the `_embedding_unavailable` flag is set in `DocumentDBSearchRepository`
2. **Fallback**: All subsequent searches skip embedding generation and use `_lexical_only_search()` instead
3. **Error Caching**: The `SentenceTransformersClient` caches load errors in `_load_error` to avoid repeated download attempts (e.g., hitting HuggingFace on every call)
4. **Indexing**: When the model is unavailable during startup, servers and agents are indexed without embeddings. Documents are stored with empty embedding vectors
5. **Response**: The API response includes a `search_mode` field set to `"lexical-only"` (instead of the normal `"hybrid"`) so callers know the search quality is reduced

### Lexical-Only Search Flow

```
                          +-------------------+
                          |   Search Query    |
                          |  "context7 docs"  |
                          +--------+----------+
                                   |
                                   v
                       +-----------------------+
                       | Embedding Model Check |
                       | _embedding_unavailable|
                       | == True?              |
                       +-----------+-----------+
                                   |
                          Yes (fallback)
                                   |
                                   v
                       +-----------------------+
                       |  Keyword Tokenization |
                       |  ["context7", "docs"] |
                       +-----------+-----------+
                                   |
                                   v
                       +-----------------------+
                       |  MongoDB Aggregation  |
                       |  $regexMatch on path, |
                       |  name, description,   |
                       |  tags, tools          |
                       +-----------+-----------+
                                   |
                                   v
                       +-----------------------+
                       |  Text Boost Scoring   |
                       |  Normalized by         |
                       |  MAX_LEXICAL_BOOST     |
                       |  (12.5)               |
                       +-----------+-----------+
                                   |
                                   v
                       +-----------------------+
                       |  Result Grouping      |
                       |  search_mode:         |
                       |  "lexical-only"       |
                       +-----------------------+
```

### Scoring in Lexical-Only Mode

In lexical-only mode, the text boost score is normalized to a 0-1 range using a fixed denominator (`MAX_LEXICAL_BOOST = 12.5`):

```
relevance_score = text_boost / MAX_LEXICAL_BOOST
```

The same boost weights from hybrid mode apply:

| Match Location | Boost Value |
|----------------|-------------|
| Path           | +5.0        |
| Name           | +3.0        |
| Description    | +2.0        |
| Tags           | +1.5        |
| Tool (each)    | +1.0        |

### Recovery

When the embedding model becomes available again (e.g., after a restart with correct configuration), the system automatically returns to full hybrid search mode. The `_embedding_unavailable` flag and `_load_error` cache are per-process and reset on restart.

## Performance Considerations

1. **Result Limiting**: Top 3 per entity type to reduce payload size
2. **Index Reuse**: HNSW index parameters (m=16, efConstruction=128) optimized for recall
3. **Embedding Caching**: Lazy-loaded model with singleton pattern
4. **Keyword Fallback**: Separate query ensures explicit matches are not missed
5. **Error Caching**: Failed model loads are cached to avoid repeated download/API attempts

## Example: Why Hybrid Matters

Query: "context7"

- **Vector-only**: Might return documentation servers with similar semantic content
- **Keyword-only**: Finds exact match but misses related servers
- **Hybrid**: Ranks /context7 at top (keyword boost) while including semantically similar alternatives
