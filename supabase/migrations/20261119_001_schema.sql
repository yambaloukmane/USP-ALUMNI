-- AEPS-ALUMNI : nouvelles colonnes, tables, fonction SQL et espaces de stockage.
-- Idempotent : peut être relancé sans danger.

-- ---------------------------------------------------------------- Membres
alter table public.members
  add column if not exists role text not null default 'member',
  add column if not exists status text not null default 'active',
  add column if not exists linkedin text default '',
  add column if not exists is_mentor boolean not null default false;

do $$ begin
  alter table public.members add constraint members_role_check check (role in ('member', 'admin'));
exception when duplicate_object then null; end $$;
do $$ begin
  alter table public.members add constraint members_status_check check (status in ('active', 'pending', 'suspended'));
exception when duplicate_object then null; end $$;

create unique index if not exists members_email_lower_key on public.members (lower(email));
create index if not exists members_promo_idx on public.members (promo);

-- ---------------------------------------------------------------- Emplois
alter table public.jobs
  add column if not exists apply_contact text default '',
  add column if not exists expires_at date,
  add column if not exists status text not null default 'approved',
  add column if not exists posted_by text default '';
do $$ begin
  alter table public.jobs add constraint jobs_status_check check (status in ('approved', 'pending'));
exception when duplicate_object then null; end $$;

-- ---------------------------------------------------------------- Messages
alter table public.messages add column if not exists notified boolean not null default false;
create index if not exists messages_receiver_created_idx on public.messages (receiver_id, created_at desc);
create index if not exists messages_sender_created_idx on public.messages (sender_id, created_at desc);

-- ---------------------------------------------------------------- Événements
create table if not exists public.events (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  description text not null default '',
  location text not null default '',
  starts_at timestamptz not null,
  created_at timestamptz not null default now()
);
create index if not exists events_starts_at_idx on public.events (starts_at);

create table if not exists public.event_rsvps (
  event_id uuid not null references public.events (id) on delete cascade,
  member_id uuid not null references public.members (id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (event_id, member_id)
);
create index if not exists event_rsvps_member_idx on public.event_rsvps (member_id);

-- ---------------------------------------------------------------- Cotisations
create table if not exists public.dues (
  id uuid primary key default gen_random_uuid(),
  member_id uuid not null references public.members (id) on delete cascade,
  year integer not null,
  amount integer not null check (amount > 0),
  status text not null default 'pending' check (status in ('pending', 'paid')),
  method text not null default '',
  reference text unique,
  paid_at timestamptz,
  created_at timestamptz not null default now(),
  unique (member_id, year)
);
create index if not exists dues_year_idx on public.dues (year);

-- ---------------------------------------------------------------- Galerie
create table if not exists public.photos (
  id uuid primary key default gen_random_uuid(),
  album text not null default 'Général',
  title text not null default '',
  url text not null,
  path text not null,
  uploaded_by uuid references public.members (id) on delete set null,
  created_at timestamptz not null default now()
);
create index if not exists photos_created_idx on public.photos (created_at desc);

-- ---------------------------------------------------------------- Résumé des conversations
-- Renvoie, pour chaque interlocuteur : dernier message et nombre de non lus,
-- en une seule requête (au lieu de relire des centaines de messages).
create or replace function public.conversation_summaries(me text)
returns table (peer text, last_text text, last_time text, last_at timestamptz, unread bigint)
language sql
stable
set search_path = public
as $$
  with mine as (
    select case when sender_id = me then receiver_id else sender_id end as peer,
           text, "time" as msg_time, created_at
    from messages
    where (sender_id = me or receiver_id = me) and receiver_id not like 'promo:%'
  ),
  last_msg as (
    select distinct on (peer) peer, text, msg_time, created_at
    from mine
    order by peer, created_at desc
  ),
  unread_msg as (
    select sender_id as peer, count(*) as n
    from messages
    where receiver_id = me and is_read = false
    group by sender_id
  )
  select l.peer, l.text, l.msg_time, l.created_at, coalesce(u.n, 0)
  from last_msg l
  left join unread_msg u on u.peer = l.peer
$$;
revoke all on function public.conversation_summaries(text) from public, anon, authenticated;
grant execute on function public.conversation_summaries(text) to service_role;

-- ---------------------------------------------------------------- Stockage de fichiers
insert into storage.buckets (id, name, public)
values ('avatars', 'avatars', true), ('voice', 'voice', true), ('gallery', 'gallery', true)
on conflict (id) do nothing;
