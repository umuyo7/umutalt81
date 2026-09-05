#!/usr/bin/env sh
set -eu

backup_dir="/opt/backups/restaurant-catering"
project_dir="/opt/restaurant-catering"
stamp="$(date +%F-%H%M%S)"
raw_file="$backup_dir/.postgres-$stamp.sql"
final_file="$backup_dir/postgres-$stamp.sql.gz"
mysql_raw_file="$backup_dir/.catering-$stamp.sql"
mysql_final_file="$backup_dir/catering-$stamp.sql.gz"

umask 077
mkdir -p "$backup_dir"
trap 'rm -f "$raw_file" "$final_file" "$mysql_raw_file" "$mysql_final_file"' EXIT HUP INT TERM

set -a
. "$project_dir/.env"
set +a

docker compose -f "$project_dir/docker-compose.yml" exec -T db \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > "$raw_file"
test -s "$raw_file"
gzip -c "$raw_file" > "$final_file"
gzip -t "$final_file"
rm -f "$raw_file"

docker compose -f "$project_dir/docker-compose.yml" exec -T catering_db \
  sh -c 'mariadb-dump -u"$MARIADB_USER" -p"$MARIADB_PASSWORD" "$MARIADB_DATABASE"' > "$mysql_raw_file"
test -s "$mysql_raw_file"
gzip -c "$mysql_raw_file" > "$mysql_final_file"
gzip -t "$mysql_final_file"
rm -f "$mysql_raw_file"
trap - EXIT HUP INT TERM

find "$backup_dir" -type f \( -name 'postgres-*.sql.gz' -o -name 'catering-*.sql.gz' \) -mtime +30 -delete
