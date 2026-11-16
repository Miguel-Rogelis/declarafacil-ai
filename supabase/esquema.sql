-- DeclaraFácil: una declaración guardada por persona.
-- Pégalo completo en Supabase → SQL Editor → New query → Run. Se puede correr más de una vez.

create table if not exists public.declaraciones (
  user_id uuid primary key references auth.users (id) on delete cascade default auth.uid(),
  datos jsonb not null,
  actualizada timestamptz not null default now()
);

-- Seguridad por filas: cada persona solo ve, crea, cambia y borra la suya
alter table public.declaraciones enable row level security;

drop policy if exists "ver la mía" on public.declaraciones;
drop policy if exists "crear la mía" on public.declaraciones;
drop policy if exists "cambiar la mía" on public.declaraciones;
drop policy if exists "borrar la mía" on public.declaraciones;

create policy "ver la mía" on public.declaraciones for select to authenticated using ((select auth.uid()) = user_id);
create policy "crear la mía" on public.declaraciones for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "cambiar la mía" on public.declaraciones for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "borrar la mía" on public.declaraciones for delete to authenticated using ((select auth.uid()) = user_id);
