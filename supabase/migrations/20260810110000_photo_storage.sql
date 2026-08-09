-- Три приватных бакета фотоконтроля (план §4, таблица Storage).
-- HEIC/HEIF в whitelist — без него загрузка с айфона падает на первом клиенте.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  ('packaging-artwork', 'packaging-artwork', false, 52428800,
   array['application/pdf']),
  ('packaging-photos', 'packaging-photos', false, 10485760,
   array['image/jpeg', 'image/png', 'image/heic', 'image/heif']),
  ('evidence-crops', 'evidence-crops', false, 2097152,
   array['image/jpeg', 'image/png'])
on conflict (id) do nothing;

-- Политики: владелец префикса <uid>/... читает и пишет своё; всё остальное закрыто.
-- Кропы пользователь только читает: пишет их сервер (service_role, мимо RLS).
create policy "photo owners read" on storage.objects
  for select to authenticated
  using (bucket_id in ('packaging-artwork', 'packaging-photos', 'evidence-crops')
         and (storage.foldername(name))[1] = auth.uid()::text);

create policy "photo owners upload" on storage.objects
  for insert to authenticated
  with check (bucket_id in ('packaging-artwork', 'packaging-photos')
              and (storage.foldername(name))[1] = auth.uid()::text);

-- update/delete намеренно НЕ выдаются: кадры immutable, удаляет ретеншн-джоба.
