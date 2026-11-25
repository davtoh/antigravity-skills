# Search Migration Plan

## Context
Move the search service from REST handlers to a GraphQL resolver layer.

### Milestone 1: Contracts & Schema
- [x] **src/search/schema.graphql**: define Query.search and SearchResult types
- [x] **src/search/types.py**: add dataclasses mirroring the schema

### Milestone 2: Resolvers
- [ ] **src/search/resolvers.py**: implement Query.search resolver delegating to existing service
- [ ] **src/search/pagination.py**: add cursor pagination helper
- [ ] **tests/test_resolvers.py**: unit tests for resolver and pagination edge cases
- [ ] **docs/search_graphql.md**: document the resolver contract

### Milestone 3: Client Cutover (Deferred to Next Milestone)
- [ ] **web/src/search/client.ts**: switch fetch calls to GraphQL
- [ ] **tests/e2e/test_search_cutover.py**: end-to-end check
