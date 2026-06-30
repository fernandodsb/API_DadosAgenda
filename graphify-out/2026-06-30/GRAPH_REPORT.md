# Graph Report - C:\Users\fernando.brito\PycharmProjects\API_DadosAgenda  (2026-06-30)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 98 nodes · 129 edges · 12 communities (10 shown, 2 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 3 edges (avg confidence: 0.95)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `573f638f`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]

## God Nodes (most connected - your core abstractions)
1. `check_admin_status()` - 8 edges
2. `fetch_sagicon_data_from_db_for_agenda()` - 6 edges
3. `validate_dates()` - 6 edges
4. `process_and_merge_data_in_memory()` - 5 edges
5. `check_admin_permission()` - 5 edges
6. `run_atualizacao_cache_diaria()` - 5 edges
7. `Graphify Skill Definition` - 5 edges
8. `are_names_partially_equal()` - 4 edges
9. `fetch_raw_agenda_events_from_db()` - 4 edges
10. `update_dado_diferente_in_db()` - 4 edges

## Surprising Connections (you probably didn't know these)
- `run_atualizacao_cache_diaria()` --calls--> `fetch_raw_agenda_events_from_db()`  [EXTRACTED]
  atualizar_cache_agenda_diaria.py → api_dados_integrado.py
- `run_atualizacao_cache_diaria()` --calls--> `fetch_sagicon_data_from_db_for_agenda()`  [EXTRACTED]
  atualizar_cache_agenda_diaria.py → api_dados_integrado.py
- `run_atualizacao_cache_diaria()` --calls--> `process_and_merge_data_in_memory()`  [EXTRACTED]
  atualizar_cache_agenda_diaria.py → api_dados_integrado.py
- `run_atualizacao_cache_diaria()` --calls--> `update_dado_diferente_in_db()`  [EXTRACTED]
  atualizar_cache_agenda_diaria.py → api_dados_integrado.py
- `Graphify Skill Definition` --references--> `Export and Integration Logic`  [EXTRACTED]
  .claude/skills/graphify/SKILL.md → .claude/skills/graphify/references/exports.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Graphify Core Pipeline Logic** — claude_skills_graphify_skill, claude_skills_graphify_references_extraction_spec, claude_skills_graphify_references_update [INFERRED 0.85]

## Communities (12 total, 2 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.20
Nodes (15): are_names_partially_equal(), execute_pg_query_single_row(), fetch_raw_agenda_events_from_db(), fetch_sagicon_data_from_db_for_agenda(), get_data_from_cache(), process_and_merge_data_in_memory(), Busca dados na tabela farmaceuticos_frt (Sagicon) para cada evento da agenda for, Mescla dados brutos da agenda e dados processados do Sagicón,     realiza a com (+7 more)

### Community 1 - "Community 1"
Cohesion: 0.14
Nodes (4): login(), Endpoint para autenticação de usuário.     Recebe JSON com 'username' e 'passwo, connect_db(), Estabelece e retorna a conexão e o cursor do banco de dados.

### Community 2 - "Community 2"
Cohesion: 0.26
Nodes (14): check_admin_status(), fetch_distinct_options(), get_atendimentos_dados_diferentes(), get_atendimentos_por_localidade(), get_atendimentos_por_servico(), get_atividades_usuarios(), get_eventos_filtrados(), get_opcoes_localidades() (+6 more)

### Community 3 - "Community 3"
Cohesion: 0.19
Nodes (12): are_names_partially_equal(), execute_pg_query_single_row(), fetch_raw_agenda_events_from_db_historic(), fetch_sagicon_data_from_db_for_agenda(), process_and_merge_data_in_memory(), Busca dados do Sagicon (farmaceuticos_frt) para os eventos da agenda fornecidos., Mescla dados e recalcula 'dado_diferente'., Atualiza o campo 'dado_diferente' no banco de dados em lotes. (+4 more)

### Community 4 - "Community 4"
Cohesion: 0.15
Nodes (10): get_calendar_service(), Autentica com a Google Calendar API e retorna o objeto de serviço., fetch_events_from_calendar(), process_events_for_db(), Busca eventos de um calendário específico em um range de tempo com paginação., Processa a lista de eventos buscados, aplicando lógica condicional por calendári, fetch_events_from_calendar(), process_events_for_db() (+2 more)

### Community 5 - "Community 5"
Cohesion: 0.20
Nodes (10): Ingestion and Watch Logic, Export and Integration Logic, Extraction Specification, Query and Traversal Logic, Transcription Logic, Incremental Update Logic, Graphify Skill Definition, Incremental Build Pattern (+2 more)

### Community 6 - "Community 6"
Cohesion: 0.53
Nodes (5): alterar_usuario(), check_admin_permission(), criar_usuario(), listar_usuarios(), Verifica se o usuário que está fazendo a requisição tem permissão para gerenciar

### Community 7 - "Community 7"
Cohesion: 0.40
Nodes (4): fetch_events_from_calendar(), process_events_for_db(), Busca eventos de um calendário específico em um range de tempo com paginação., Processa a lista de eventos buscados, aplicando lógica condicional por calendári

## Knowledge Gaps
- **9 isolated node(s):** `Extraction Specification`, `Export and Integration Logic`, `Transcription Logic`, `Ingestion and Watch Logic`, `GitHub and Multi-Repo Logic` (+4 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What connects `Compara dois nomes, normalizando-os (removendo acentos, espaços extras, case-ins`, `Executa uma consulta PostgreSQL e retorna o primeiro registro como dicionário.`, `Busca eventos brutos da tabela calendar_events no PostgreSQL,     filtrando ape` to the rest of the system?**
  _35 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.14285714285714285 - nodes in this community are weakly interconnected._