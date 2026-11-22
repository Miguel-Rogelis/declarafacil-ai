-- DeclaraFácil: una declaración por persona y por año, y una carpeta privada con sus documentos.
-- Pégalo completo en Supabase → SQL Editor → New query → Run. Se puede correr más de una vez.

-- 1. Declaraciones (una fila por persona y año gravable)
create table if not exists public.declaraciones (
  user_id uuid not null references auth.users (id) on delete cascade default auth.uid(),
  anio int,
  datos jsonb not null,
  actualizada timestamptz not null default now()
);

-- Si la tabla venía de la versión anterior (una sola declaración por persona), se le agrega el año
alter table public.declaraciones add column if not exists anio int;
update public.declaraciones set anio = coalesce((datos ->> 'anio')::int, 2025) where anio is null;
alter table public.declaraciones alter column anio set not null;
alter table public.declaraciones drop constraint if exists declaraciones_pkey;
alter table public.declaraciones add constraint declaraciones_pkey primary key (user_id, anio);

-- Seguridad por filas: cada persona solo ve, crea, cambia y borra las suyas
alter table public.declaraciones enable row level security;

drop policy if exists "ver la mía" on public.declaraciones;
drop policy if exists "crear la mía" on public.declaraciones;
drop policy if exists "cambiar la mía" on public.declaraciones;
drop policy if exists "borrar la mía" on public.declaraciones;

create policy "ver la mía" on public.declaraciones for select to authenticated using ((select auth.uid()) = user_id);
create policy "crear la mía" on public.declaraciones for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "cambiar la mía" on public.declaraciones for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "borrar la mía" on public.declaraciones for delete to authenticated using ((select auth.uid()) = user_id);

-- 2. Documentos: espacio privado «documentos», cada persona en su carpeta {su id}/{año}/
insert into storage.buckets (id, name, public, file_size_limit)
values ('documentos', 'documentos', false, 15728640)
on conflict (id) do update set public = false, file_size_limit = 15728640;

drop policy if exists "docs: ver los míos" on storage.objects;
drop policy if exists "docs: subir los míos" on storage.objects;
drop policy if exists "docs: cambiar los míos" on storage.objects;
drop policy if exists "docs: borrar los míos" on storage.objects;

create policy "docs: ver los míos" on storage.objects for select to authenticated
  using (bucket_id = 'documentos' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy "docs: subir los míos" on storage.objects for insert to authenticated
  with check (bucket_id = 'documentos' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy "docs: cambiar los míos" on storage.objects for update to authenticated
  using (bucket_id = 'documentos' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy "docs: borrar los míos" on storage.objects for delete to authenticated
  using (bucket_id = 'documentos' and (storage.foldername(name))[1] = (select auth.uid())::text);

-- 3. Solo para el servidor (clave de servicio): configuración editable con historial, métricas sin datos
--    personales y contadores del cupo de IA. RLS activo y SIN políticas: el navegador no las puede leer.
create table if not exists public.df_config (
  clave text primary key,
  datos jsonb not null,
  autor text,
  actualizada timestamptz not null default now()
);
create table if not exists public.df_config_historial (
  id bigint generated always as identity primary key,
  clave text not null,
  datos jsonb not null,
  autor text,
  creada timestamptz not null default now()
);
create index if not exists df_config_historial_clave on public.df_config_historial (clave, id desc);
create table if not exists public.df_metricas (
  id bigint generated always as identity primary key,
  sesion text,
  tipo text not null,
  datos jsonb not null,
  creado timestamptz not null default now()
);
create index if not exists df_metricas_creado on public.df_metricas (creado);
alter table public.df_config enable row level security;
alter table public.df_config_historial enable row level security;
alter table public.df_metricas enable row level security;
