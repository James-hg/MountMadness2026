# Goals Feature (`/goals`)

## Overview

The Goals module lets users create and track savings goals with computed progress and monthly recommendations.

- Auth required on all endpoints.
- User ownership enforced in every query.
- Money contract follows existing backend standard: `NUMERIC(12,2)` serialized as decimal strings.

## Endpoints

- `POST /goals`
- `GET /goals?status=active|paused|completed|cancelled|all`
- `GET /goals/{goal_id}`
- `PATCH /goals/{goal_id}`
- `DELETE /goals/{goal_id}`

## Computed Fields

Returned with every goal:

- `remaining_amount`
- `months_left`
- `recommended_monthly_save_amount`
- `progress_pct`
- `on_track`
- `shortfall_amount`

Computation highlights:

- `months_left = ceil(days_left / 30)` with lower bound `0`.
- `recommended_monthly_save_amount` is only non-zero for `active` goals with remaining balance.
- `progress_pct` is floored and capped `0..100`.
- `on_track` compares current saved amount to expected linear progress since goal creation.

## AI Tool Hook Mapping

These endpoints are intentionally tool-friendly for future AI assistant calls:

- `create_goal` -> `POST /goals`
- `list_goals` -> `GET /goals`
- `update_goal_saved` -> `PATCH /goals/{goal_id}` with `saved_amount`
- `get_goal_plan` -> `GET /goals/{goal_id}` (includes computed fields)

## Goals Chatbot (`POST /goals/chat`)

Dedicated goals assistant endpoint for planning and goal updates:

- request: `{ "message": "...", "pending_action": null }`
- response:
  - `reply`
  - `conversation_id` (`"stateless"`)
  - `actions`
  - `needs_confirmation`
  - `pending_action` (only when confirmation is required)

Behavior:

- Stateless by design: no DB-backed chat history and no localStorage history in goals chat UI.
- Read scope: goals + compact financial snapshot/trend aggregates.
- Write actions are always preview-first and require explicit confirmation.
- Delete is supported but still requires confirmation.
