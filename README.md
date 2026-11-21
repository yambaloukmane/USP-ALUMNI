# AEPS-ALUMNI — version Django

Réécriture complète en Python (Django) du site Next.js `usp-alumini`.
La base de données reste **Supabase** (tables `members`, `news`, `jobs`, `messages`) ; Django n'a pas de base locale.

## Installation

```bash
python -m venv venv
source venv/bin/activate          # Windows : venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # puis renseigner les valeurs
python manage.py runserver
```

Ouvrir http://127.0.0.1:8000

## Variables d'environnement (.env)

| Variable | Rôle |
|---|---|
| `SUPABASE_URL`, `SUPABASE_KEY` | accès à votre projet Supabase |
| `ADMIN_PASSWORD` | mot de passe de l'espace `/responsable/` (plus codé en dur) |
| `DJANGO_SECRET_KEY` | clé secrète (obligatoire en production) |
| `DJANGO_DEBUG` | `1` en développement, `0` en production |
| `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` | domaines autorisés en production |
| `EMAIL_*`, `DEFAULT_FROM_EMAIL` | envoi du code de vérification à l'inscription (en développement, le code s'affiche dans la console) |

## Pages

`/` accueil · `/about/` · `/services/` · `/contact/` · `/feed/` actualités & emplois · `/members/` annuaire ·
`/treasury/` · `/login/` · `/register/` · `/profile/` · `/messages/` · `/responsable/` administration.

## Changements par rapport à la version Next.js

- Mots de passe **hachés** (les anciens mots de passe en clair sont convertis automatiquement à la première connexion).
- Mot de passe responsable lu dans `ADMIN_PASSWORD`, vérifié côté serveur.
- Inscription avec code de vérification par e-mail (15 min, 5 essais).
- Session par cookie signé, protection CSRF, requêtes Supabase validées.
- La messagerie interroge le serveur toutes les quelques secondes (pas de requête globale de toutes les données).

## Supabase

La colonne `members.password` contient désormais des hachés : elle doit rester de type `text`.
Les politiques RLS doivent autoriser les opérations utilisées avec votre clé (voir l'ancien `SUPABASE_SETUP.md`).
Idéalement, utilisez la clé `service_role` côté serveur uniquement (jamais exposée au navigateur) et fermez l'accès public à la table `members`.

## Production

```bash
DJANGO_DEBUG=0 gunicorn config.wsgi
```

## E-mails réels (code de vérification)

Renseignez `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` (mot de passe d'application Gmail) et `DEFAULT_FROM_EMAIL` dans `.env`, puis testez :

```bash
python manage.py send_test_email votre.adresse@exemple.com
```

---

## Version 3 — nouveautés

**Sécurité (à faire une fois)**
1. Supabase > SQL Editor : exécutez `supabase/migrations/20261119_001_schema.sql` (déjà appliquée sur votre projet), puis `20261119_002_rls.sql` (active la sécurité par ligne : l'ancienne clé publique ne donne plus accès aux données).
2. Supabase > Project Settings > API : copiez la clé **service_role** dans `.env` (`SUPABASE_KEY=`). Elle reste côté serveur, ne la publiez jamais (ni GitHub, ni navigateur).
3. Relancez le site.

**Fonctions** : mot de passe oublié, validation des inscriptions (`REQUIRE_APPROVAL=1`), rôles admin, tableau de bord, export CSV, offres (postuler, expiration, proposition par les membres), événements + inscriptions, cotisations (paiement CinetPay), galerie, mentors + LinkedIn, discussion de groupe par promotion, messages vocaux dans Supabase Storage, application installable (PWA).

**Qualité** : `python manage.py test alumni` · `ruff check .` · `docker compose up --build` · CI GitHub dans `.github/workflows/ci.yml`.

**Résumé par e-mail** (à planifier chaque semaine avec cron ou le planificateur de votre hébergeur) :
`python manage.py send_digests`
Test d'envoi : `python manage.py send_test_email vous@exemple.com`.

**Mise à jour d'une installation existante** : extrayez le zip par-dessus votre dossier en gardant `.env` et `venv`, puis `pip install -r requirements.txt`.

**Limites connues** : pas de carte des membres ni de temps réel Supabase (messages rafraîchis toutes les 3–15 s) ; paiement CinetPay à tester avec votre compte marchand et une adresse publique (pas de localhost) ; buckets de stockage publics (adresses non devinables) ; sans Redis le cache est propre à chaque processus ; Gmail limite le volume d'envoi.

**Design** : charte bleu ciel (couleur d'origine) + encre bleu nuit, polices Sora et Figtree. Les styles sont dans `frontend/input.css` ; après modification, recompilez avec
`npx @tailwindcss/cli -i frontend/input.css -o alumni/static/alumni/css/tailwind.css --minify`
(nécessite Node.js et `npm i tailwindcss @tailwindcss/cli`).

## Formulaire d'inscription en 4 étapes (migration 003)

Champs : compte (prénom, nom, e-mail, téléphone + WhatsApp, mot de passe de 8 caractères minimum), prépa (promotion, année d'entrée, filière, école intégrée, filière à l'école, référent), situation (statut, poste, entreprise, secteur, pays, ville), réseau (offres, recherches, LinkedIn, bio, visibilité e-mail/téléphone, conditions).

Exécutez **`supabase/migrations/20261120_003_profile_fields.sql`** dans le SQL Editor de Supabase. Tant qu'elle n'est pas appliquée, le site fonctionne mais les nouveaux champs ne sont pas enregistrés (un bandeau l'indique dans l'espace responsable).
Le référent n'est visible que des administrateurs ; l'e-mail et le téléphone n'apparaissent dans l'annuaire que si le membre l'a choisi.
