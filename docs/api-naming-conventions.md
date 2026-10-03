# FastAPI Naming Conventions & Best Practices

This document defines the strict naming conventions and architectural standards for developing the REST API using FastAPI, Pydantic, SQLAlchemy, and standard Python conventions (PEP 8). All generated code must adhere strictly to these rules.

## 0. General Rule: Clarity and Descriptiveness
* **Meaningful Names:** Always use clear, fully descriptive names for files, functions, classes, and variables. Avoid ambiguous terms, single-letter variables (except for standard loop counters like `i` or `j`), and cryptic abbreviations. Code should be self-documenting and reveal its intention immediately.
  * *Correct:* `user_account_balance`, `calculate_monthly_revenue()`, `ActiveSubscriptionRepository`.
  * *Incorrect:* `usr_bal`, `calc()`, `repo`.

## 1. Files and Modules (`snake_case`)

* **Python Files & Modules:** Use lowercase letters and underscores (`snake_case`).

  * *Examples:* `users_router.py`, `database.py`, `auth_service.py`, `item_model.py`.

## 2. Classes and Models (`PascalCase`)

* **Pydantic Schemas / DTOs:** Use `PascalCase`. Schema names must clearly state their exact data purpose (input, output, or database representation).

  * *Request/Input:* `UserCreate`, `ItemUpdate`

  * *Response/Output:* `UserResponse`, `ItemInDB`, `UserPublic`

* **SQLAlchemy / ORM Models:** Use `PascalCase` in the singular form representing the domain entity.

  * *Examples:* `class User(Base):`, `class Item(Base):`

## 3. Functions, Endpoints, and Variables (`snake_case`)

* **Functions and Methods:** Use descriptive names in `snake_case`.

  * *Examples:* `get_user_by_id()`, `hash_password()`.

* **Path Operations (FastAPI Endpoints):** The path operation function name must describe the business action and the target resource.

  * *Examples:* `async def get_active_users():`, `async def create_new_item():`.

* **Variables and Constants:** Standard variables use `snake_case`; global constants use uppercase `UPPER_CASE`.

  * *Examples:* `max_retry_attempts = 3`, `DEFAULT_PAGE_SIZE = 50`.

## 4. API Routes and URIs (`kebab-case` and Plurals)

* **Paths (URLs):** Use plural resource names and `kebab-case` for multi-word paths. **Never use verbs in the URL path** (HTTP methods handle the action: `GET`, `POST`, `PUT`, `DELETE`).

  * *Correct:* `/users`, `/users/{user_id}`, `/user-profiles`, `/order-items/{item_id}`

  * *Incorrect:* `/getUsers`, `/createUser`, `/user_items`

## 5. Parameters and JSON Fields (`snake_case` / `camelCase`)

* **Python Parameters:** Path, query, and body parameters in Python code must use `snake_case`.

  * *Example:* `async def get_users(skip_items: int = 0, limit_count: int = 10):`

* **JSON Serialization:** JSON payloads exposed to clients should match the architectural standard (typically `camelCase` for modern frontends or `snake_case` for strict backend parity). If Pydantic v2 is used, implement an `alias_generator` globally if `camelCase` output is desired while keeping Python properties in `snake_case`.

## 6. Enums

* **Enumerations:** The Enum class name must be in `PascalCase`, and its members must be in `UPPER_SNAKE_CASE` with clean string values.

  * *Example:*

    ```
    class UserRole(str, Enum):
        ADMIN = "admin"
        REGULAR_USER = "regular_user"
    