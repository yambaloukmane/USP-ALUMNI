-- Sécurité : active la sécurité par ligne (RLS) sur TOUTES les tables.
-- Sans politique, seuls les accès avec la clé « service_role » (serveur Django) passent.
-- La clé publique (anon) ne peut plus rien lire ni modifier.
alter table public.members enable row level security;
alter table public.messages enable row level security;
alter table public.news enable row level security;
alter table public.jobs enable row level security;
alter table public.events enable row level security;
alter table public.event_rsvps enable row level security;
alter table public.dues enable row level security;
alter table public.photos enable row level security;
