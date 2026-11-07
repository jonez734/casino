#!/usr/bin/env bash
# clean-spin-scratch.sh -- remove the scratch rows left by scripts/check-spin-retry.py.
#
# The checker creates members, accounts, a table, spins, and transactions whose names start with
# retrychk_. When its cleanup is refused (for example, the member delete cascades into
# engine.map_member_flag, which some roles cannot write), those rows stay behind. This script removes
# every row whose name starts with retrychk_ and nothing else.
#
# It runs as one transaction: either every table is cleared and verified empty, or nothing is changed.
# A dry run is the default. Use --apply to delete.
#
# Usage:
#   scripts/clean-spin-scratch.sh --db <database>            # dry run: count what would be removed
#   scripts/clean-spin-scratch.sh --db <database> --apply    # remove it
#
# Connection settings come from psql's environment (PGHOST, PGPORT, PGUSER, PGPASSWORD, ~/.pgpass,
# or peer auth). The script never takes a password. Run it as a role that can delete from the
# casino, bank, and engine tables (for example the database owner, jam).
#
# Exit status: 0 on success, 1 when rows remain after the delete (the transaction is rolled back),
# 2 on usage or connection errors.

set -uo pipefail

PREFIX="retrychk_"
DB=""
APPLY=0

usage() {
    sed -n '3,19p' "$0" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
    case "$1" in
        --db) [ $# -ge 2 ] || { echo "clean-spin-scratch: --db needs a value" >&2; exit 2; }; DB="$2"; shift 2 ;;
        --apply) APPLY=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "clean-spin-scratch: unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

[ -n "$DB" ] || { echo "clean-spin-scratch: --db is required" >&2; usage >&2; exit 2; }
command -v psql >/dev/null 2>&1 || { echo "clean-spin-scratch: psql not found" >&2; exit 2; }

PSQL=(psql -X -q -At -v ON_ERROR_STOP=1 -v "prefix=${PREFIX}" -d "$DB")

# Counting SQL, one table per row. Used by the dry run and to report what remains after an apply.
count_sql() {
cat <<SQL
select 'casino.__slot_spin' as tbl, count(*) from casino.__slot_spin where left(player_moniker::text, length('${PREFIX}')) = '${PREFIX}'
union all select 'casino.__bank_table', count(*) from casino.__bank_table where left(table_moniker::text, length('${PREFIX}')) = '${PREFIX}'
union all select 'bank.__transaction', count(*) from bank.__transaction t
    where left(t.membermoniker::text, length('${PREFIX}')) = '${PREFIX}'
       or t.accountid in (select id from bank.__account where left(moniker::text, length('${PREFIX}')) = '${PREFIX}')
union all select 'bank.__account', count(*) from bank.__account where left(moniker::text, length('${PREFIX}')) = '${PREFIX}'
union all select 'casino.__player', count(*) from casino.__player where left(moniker::text, length('${PREFIX}')) = '${PREFIX}'
union all select 'casino.__table', count(*) from casino.__table where left(moniker::text, length('${PREFIX}')) = '${PREFIX}'
union all select 'engine.__bed_token', count(*) from engine.__bed_token where left(moniker::text, length('${PREFIX}')) = '${PREFIX}'
union all select 'engine.map_member_flag', count(*) from engine.map_member_flag where left(moniker::text, length('${PREFIX}')) = '${PREFIX}'
union all select 'engine.__member', count(*) from engine.__member where left(moniker::text, length('${PREFIX}')) = '${PREFIX}';
SQL
}

# Delete in dependency order, then verify nothing matches. The whole script is one transaction, so a
# refused statement or a non-empty verify rolls back every delete.
apply_sql() {
cat <<SQL
begin;
delete from casino.__slot_spin where left(player_moniker::text, length('${PREFIX}')) = '${PREFIX}';
delete from casino.__bank_table where left(table_moniker::text, length('${PREFIX}')) = '${PREFIX}';
delete from bank.__transaction t
    where left(t.membermoniker::text, length('${PREFIX}')) = '${PREFIX}'
       or t.accountid in (select id from bank.__account where left(moniker::text, length('${PREFIX}')) = '${PREFIX}');
delete from bank.__account where left(moniker::text, length('${PREFIX}')) = '${PREFIX}';
delete from casino.__player where left(moniker::text, length('${PREFIX}')) = '${PREFIX}';
delete from casino.__table where left(moniker::text, length('${PREFIX}')) = '${PREFIX}';
delete from engine.__bed_token where left(moniker::text, length('${PREFIX}')) = '${PREFIX}';
delete from engine.map_member_flag where left(moniker::text, length('${PREFIX}')) = '${PREFIX}';
delete from engine.__member where left(moniker::text, length('${PREFIX}')) = '${PREFIX}';
do \$check\$
declare
    leftover bigint;
begin
    select
        (select count(*) from casino.__slot_spin where left(player_moniker::text, length('${PREFIX}')) = '${PREFIX}')
      + (select count(*) from casino.__bank_table where left(table_moniker::text, length('${PREFIX}')) = '${PREFIX}')
      + (select count(*) from bank.__account where left(moniker::text, length('${PREFIX}')) = '${PREFIX}')
      + (select count(*) from casino.__player where left(moniker::text, length('${PREFIX}')) = '${PREFIX}')
      + (select count(*) from casino.__table where left(moniker::text, length('${PREFIX}')) = '${PREFIX}')
      + (select count(*) from engine.__bed_token where left(moniker::text, length('${PREFIX}')) = '${PREFIX}')
      + (select count(*) from engine.map_member_flag where left(moniker::text, length('${PREFIX}')) = '${PREFIX}')
      + (select count(*) from engine.__member where left(moniker::text, length('${PREFIX}')) = '${PREFIX}')
    into leftover;
    if leftover <> 0 then
        raise exception 'scratch rows remain (%); rolled back', leftover;
    end if;
end
\$check\$;
commit;
SQL
}

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

if [ "$APPLY" -eq 0 ]; then
    echo "dry run on $DB (prefix ${PREFIX}); rows that would be removed:"
    count_sql > "$TMP"
    "${PSQL[@]}" -F $'\t' -f "$TMP" | awk -F'\t' '{ printf "  %-24s %s\n", $1, $2 }' || exit 2
    echo "nothing changed. Run again with --apply to remove them."
    exit 0
fi

echo "applying to $DB (prefix ${PREFIX}), one transaction:"
apply_sql > "$TMP"
if ! "${PSQL[@]}" -f "$TMP" 2>&1; then
    echo "clean-spin-scratch: FAILED; nothing was removed (the transaction rolled back)." >&2
    echo "The error above names the refused statement. Run this as a role that can delete from" >&2
    echo "engine.map_member_flag and the other tables, then run the script again." >&2
    exit 1
fi

echo "verified: no ${PREFIX}* rows remain. Counts after clean-up:"
count_sql > "$TMP"
"${PSQL[@]}" -F $'\t' -f "$TMP" | awk -F'\t' '{ printf "  %-24s %s\n", $1, $2 }' || exit 2
exit 0
