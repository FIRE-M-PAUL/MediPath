# MediPath demo accounts

Use these for presentations and local testing. **Change or disable in production.**

Server API base: `http://127.0.0.1:5005/api` (default Flask port).

---

## Admin (web portal)

| Field | Value |
|--------|--------|
| Page | `admin/admin-login.html` |
| Email | `admin@medipath.health` |
| Password | `admin123` |
| Role | Choose **Admin** on the login form if applicable |

Academic-style admin (separate table): username `admin`, password `admin123` on flows that use `/api/academic/login` with role `admin`.

---

## Seeded clinical doctors (Find Doctor + patient booking)

These exist in the **`DOCTOR`** table and appear in **Find Doctor** (`user/doctors.html`) via `GET /api/doctors`. Patients book with the **clinical `id`** returned there (same as `doctor_id` in `POST /api/clinical/appointments`).

Each row is linked to an **approved** `User` with role `doctor` so the same email works on **Doctor login**.

| Doctor | Email (login) | Doctor portal password | Clinical `doctor_id` (booking) |
|--------|----------------|-------------------------|--------------------------------|
| Dr. John Banda (Cardiology) | `john.banda@medipath.local` | `DemoDoctor2026!` | `1` |
| Dr. Mary Phiri (Pediatrics) | `mary.phiri@medipath.local` | `DemoDoctor2026!` | `2` |
| Dr. Peter Mwansa (GP) | `peter.mwansa@medipath.local` | `DemoDoctor2026!` | `3` |
| Dr. Grace Tembo (Dermatology) | `grace.tembo@medipath.local` | `DemoDoctor2026!` | `4` |
| Dr. Kelvin Zulu (Surgery) | `kelvin.zulu@medipath.local` | `DemoDoctor2026!` | `5` |
| Dr. Ruth Mulenga (Dentist) | `ruth.mulenga@medipath.local` | `DemoDoctor2026!` | `6` |

IDs assume a fresh seed order from `ensure_clinical_doctors_seeded()`. If your database already had doctors, confirm IDs in **Admin → Verify Physicians → Seeded clinical doctors**.

**Doctor portal:** open `doctor/doctor-login.html`, enter the email and **`DemoDoctor2026!`**.

**Academic API only** (does **not** set the browser session for the doctor SPA): `POST /api/academic/login` with `role: "doctor"`, `username` = email above, `password` = **`doctor123`** (stored on the `DOCTOR` row).

After `init_db`, exact **`clinical_doctor_id`** values are listed under **Admin → Verify Physicians** in the **Seeded clinical doctors** card.

---

## Patient demo

Register a patient via `user/register.html` or use any existing patient account. Password rules: at least 8 characters with upper, lower, and a number.

To book as a patient: log in at `user/login.html`, open **Appointments** / **Find Doctor**, pick a doctor from the list, and submit booking (uses `POST /api/clinical/appointments`).

---

## Where things show up

| Area | What you see |
|------|----------------|
| Database | `DOCTOR` rows + linked `users` / `doctor_profiles` (`clinical_doctor_id`) |
| Admin | **Seeded clinical doctors** table + **Physician Directory** tab (approved portal doctors) |
| Find Doctor | Same clinical list from `GET /api/doctors` |
| Doctor dashboard | `GET /api/clinical/appointments` scoped to the logged-in doctor’s `clinical_doctor_id` |

---

## Troubleshooting

1. **Doctor login fails** — Run the backend once so `init_db()` runs; it calls `ensure_demo_doctor_user_links()`.
2. **No appointments on doctor console** — Book as a logged-in **patient** against that doctor’s clinical id first.
3. **`clinical_doctor_id` missing in session** — Log out and log in again, or reload after `init_db` added the profile column.
