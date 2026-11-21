-- AEPS-ALUMNI : champs supplémentaires du profil (inscription en 4 étapes).
-- Idempotent : peut être relancé sans danger. À exécuter dans Supabase > SQL Editor.

alter table public.members
  add column if not exists phone_whatsapp boolean not null default false,
  add column if not exists entry_year text default '',
  add column if not exists track text default '',
  add column if not exists school text default '',
  add column if not exists school_track text default '',
  add column if not exists referent text default '',
  add column if not exists situation text default '',
  add column if not exists company text default '',
  add column if not exists offers text[] not null default '{}',
  add column if not exists seeks text[] not null default '{}',
  add column if not exists show_email boolean not null default false,
  add column if not exists show_phone boolean not null default false,
  add column if not exists terms_accepted_at timestamptz;

-- Reprise des anciens comptes : l'ancien champ « statut de formation » était stocké dans « job ».
update public.members set situation = 'Étudiant' where coalesce(situation, '') = '' and job ilike 'Étudiant%';
update public.members set is_mentor = true, offers = array_append(offers, 'mentorat')
  where is_mentor and not ('mentorat' = any(offers));

create index if not exists members_school_idx on public.members (school);
create index if not exists members_situation_idx on public.members (situation);
