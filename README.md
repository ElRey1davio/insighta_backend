# Insighta Labs+ Backend

Backend API for the Insighta Labs+ Profile Intelligence Platform. Built with Flask and SQLite.

**Live URL:** https://insightabackend-production-a89c.up.railway.app

## System Architecture

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐
│   CLI Tool   │────▶│             │     │   GitHub     │
└─────────────┘     │   Backend   │◀───▶│   OAuth      │
┌─────────────┐     │   (Flask)   │     └──────────────┘
│  Web Portal  │────▶│             │     ┌──────────────┐
└─────────────┘     │             │────▶│  External    │
                    │             │     │  APIs        │
                    └──────┬──────┘     │ (Genderize,  │
                           │            │  Agify,      │
                           ▼            │  Nationalize)│
                    ┌─────────────┐     └──────────────┘
                    │   SQLite    │
                    │   Database  │
                    └─────────────┘
```

The system follows a monolithic backend architecture. A single Flask application handles authentication, profile CRUD, natural language search, CSV export, and role-based access control. Both the CLI and web portal connect to this backend via REST API calls.

## Authentication Flow

The backend uses GitHub OAuth for authentication with PKCE support.

### Login Flow
1. Client redirects user to `GET /auth/github` which forwards to GitHub's OAuth page
2. User authenticates on GitHub
3. GitHub redirects to `GET /auth/github/callback` with an authorization code
4. Backend exchanges the code for a GitHub access token
5. Backend fetches user profile from GitHub API
6. Backend creates or updates the user in the database
7. Backend issues a JWT access token (3 min expiry) and refresh token (5 min expiry)
8. Tokens are returned to the client

### Test Code Support
For automated grading, the callback accepts `code=test_code` which returns tokens for a seeded admin user without calling GitHub APIs. Accepts optional `state` and `code_verifier` parameters.

### Token Refresh
- `POST /auth/refresh` accepts a refresh token and returns a new access/refresh token pair
- The old refresh token is immediately invalidated (rotation)
- If the refresh token is expired or invalid, the user must re-authenticate

### Logout
- `POST /auth/logout` invalidates the refresh token server-side

## API Endpoints

All `/api/*` endpoints require:
- `Authorization: Bearer <token>` header
- `X-API-Version: 1` header

### Auth
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/auth/github` | Redirect to GitHub OAuth |
| GET | `/auth/github/callback` | Handle OAuth callback |
| POST | `/auth/refresh` | Refresh token pair |
| POST | `/auth/logout` | Invalidate refresh token |

### Profiles
| Method | Endpoint | Access | Description |
|--------|----------|--------|-------------|
| GET | `/api/profiles` | All roles | List profiles (paginated, filterable) |
| GET | `/api/profiles/<id>` | All roles | Get single profile |
| GET | `/api/profiles/search?q=` | All roles | Natural language search |
| GET | `/api/profiles/export` | All roles | Export to CSV |
| POST | `/api/profiles` | Admin only | Create new profile |
| DELETE | `/api/profiles/<id>` | Admin only | Delete profile |

### Filtering & Sorting
- `gender` — male/female
- `country_id` — ISO country code (e.g., NG, KE)
- `age_group` — child/teenager/adult/senior
- `min_age`, `max_age` — age range
- `sort_by` — age, created_at, gender_probability
- `order` — asc/desc
- `page`, `limit` — pagination (max 50 per page)

### Pagination Response Format
```json
{
  "status": "success",
  "page": 1,
  "limit": 10,
  "total": 2026,
  "total_pages": 203,
  "links": {
    "self": "/api/profiles?page=1&limit=10",
    "next": "/api/profiles?page=2&limit=10",
    "prev": null
  },
  "data": [...]
}
```

## Role Enforcement

Two roles exist: `admin` and `analyst` (default).

- **Admin**: Full access — can create profiles, delete profiles, and perform all read operations
- **Analyst**: Read-only — can list, search, view, and export profiles

Role checks are implemented via middleware decorators (`@require_auth`, `@require_admin`) applied to route handlers. The user's role is embedded in the JWT token and verified on every request. Deactivated users (`is_active=false`) receive 403 on all requests.

## Natural Language Search

The `/api/profiles/search?q=` endpoint parses natural language queries into database filters:

- **Gender**: "males", "females" → filters by gender
- **Age groups**: "child", "teenager", "adult", "senior" → filters by age_group
- **Age ranges**: "above 30", "under 25" → filters by min/max age
- **Country**: "from Nigeria", "from Kenya" → maps country names to ISO codes
- **Combined**: "young males from nigeria" → gender=male, min_age=16, max_age=24, country_id=NG

The parser splits the query into words, identifies keywords, and builds SQL WHERE clauses from the extracted filters.

## Rate Limiting

| Scope | Limit |
|-------|-------|
| Auth endpoints (`/auth/*`) | 10 requests/minute |
| All other endpoints | 60 requests/minute |

Returns `429 Too Many Requests` when exceeded.

## Logging

Every request is logged with: method, endpoint, status code, and response time in milliseconds.

## Setup & Running

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your values

# Run locally
python app.py

# Production
gunicorn app:app
```

### Environment Variables
| Variable | Description |
|----------|-------------|
| `GITHUB_CLIENT_ID` | GitHub OAuth App client ID |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth App client secret |
| `JWT_SECRET` | Secret key for JWT signing |

## Database Schema

### profiles
| Field | Type |
|-------|------|
| id | UUID v7 (PK) |
| name | TEXT (unique) |
| gender | TEXT |
| gender_probability | REAL |
| age | INTEGER |
| age_group | TEXT |
| country_id | TEXT |
| country_name | TEXT |
| country_probability | REAL |
| created_at | TEXT |

### users
| Field | Type |
|-------|------|
| id | UUID v7 (PK) |
| github_id | TEXT (unique) |
| username | TEXT |
| email | TEXT |
| avatar_url | TEXT |
| role | TEXT (admin/analyst) |
| is_active | INTEGER |
| last_login_at | TEXT |
| created_at | TEXT |

### refresh_tokens
| Field | Type |
|-------|------|
| id | UUID v7 (PK) |
| user_id | TEXT |
| token | TEXT (unique) |
| expires_at | TEXT |
| created_at | TEXT |

## Tech Stack
- Python 3.12
- Flask
- SQLite
- PyJWT
- Flask-Limiter
- Gunicorn
- Railway (deployment)

## Related Repositories
- CLI: [insighta-cli](https://github.com/ElRey1davio/insighta-cli)
- Web Portal: [insighta-web](https://github.com/ElRey1davio/insighta-web)
