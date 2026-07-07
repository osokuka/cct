"""
Seed operational demo data on top of `seed_gjakova`:

  * work shifts,
  * collection & cleaning teams (with leaders + members),
  * routes mapping teams to neighbourhoods,
  * today's DailyCleaningTasks with simulated progress (done / in-progress / planned),
  * an Operations Manager user (opsmanager / ops123).

Run inside Docker (after seed_gjakova):
    docker compose exec web python manage.py seed_operations
"""

from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Team, Shift, Route, UserProfile
from accounts.task_generation import DailyCleaningTask
from locations.models import Camp, Compound, Room


class Command(BaseCommand):
    help = "Seed shifts, teams, routes, today's tasks (with progress) and an ops manager."

    def add_arguments(self, parser):
        parser.add_argument("--camp-code", default="GJ")

    def handle(self, *args, **options):
        try:
            camp = Camp.objects.get(code=options["camp_code"])
        except Camp.DoesNotExist:
            self.stderr.write("Camp not found — run `seed_gjakova` first.")
            return

        shifts = self._seed_shifts(camp)
        ops_mgr = self._seed_ops_manager(camp)
        teams = self._seed_teams(camp, shifts)
        self._seed_routes(camp, teams)
        counts = self._seed_today_tasks(camp)

        self.stdout.write(self.style.SUCCESS("Operations demo data seeded."))
        self.stdout.write(f"  Ops manager: {ops_mgr.username} / ops123")
        self.stdout.write(f"  Teams: {len(teams)} | Today's tasks: {counts['total']} "
                          f"(done {counts['done']}, in-progress {counts['in_progress']}, planned {counts['planned']})")

    # -- shifts ------------------------------------------------------------

    def _seed_shifts(self, camp):
        morning, _ = Shift.objects.get_or_create(
            camp=camp, name="Morning",
            defaults={"start_time": time(6, 0), "end_time": time(14, 0)},
        )
        afternoon, _ = Shift.objects.get_or_create(
            camp=camp, name="Afternoon",
            defaults={"start_time": time(14, 0), "end_time": time(22, 0)},
        )
        return {"morning": morning, "afternoon": afternoon}

    # -- users -------------------------------------------------------------

    def _cleaner(self, username, first, last, camp):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"first_name": first, "last_name": last, "is_active": True},
        )
        if created:
            user.set_password("cleaner123")
            user.save()
        UserProfile.objects.get_or_create(
            user=user, defaults={"role": "cleaner", "camp": camp}
        )
        return user

    def _seed_ops_manager(self, camp):
        user, created = User.objects.get_or_create(
            username="opsmanager",
            defaults={"first_name": "Operations", "last_name": "Manager", "is_active": True},
        )
        if created:
            user.set_password("ops123")
            user.save()
        profile, _ = UserProfile.objects.get_or_create(
            user=user, defaults={"role": "operations_manager", "camp": camp}
        )
        profile.role = "operations_manager"
        profile.camp = camp
        profile.save()
        return user

    # -- teams -------------------------------------------------------------

    def _seed_teams(self, camp, shifts):
        specs = [
            ("Grumbullimi Zona 1", "collection", "morning", "cz1"),
            ("Grumbullimi Zona 2", "collection", "morning", "cz2"),
            ("Grumbullimi Zona 3", "collection", "afternoon", "cz3"),
            ("Pastrimi Veri", "cleaning", "morning", "clnn"),
            ("Pastrimi Jug", "cleaning", "morning", "clns"),
        ]
        teams = {}
        for idx, (name, team_type, shift_key, slug) in enumerate(specs, start=1):
            leader = self._cleaner(f"lead_{slug}", "Lider", name.split()[-1], camp)
            m1 = self._cleaner(f"mem_{slug}_a", "Punëtor", f"{slug}A", camp)
            m2 = self._cleaner(f"mem_{slug}_b", "Punëtor", f"{slug}B", camp)
            team, _ = Team.objects.get_or_create(
                camp=camp, name=name,
                defaults={
                    "team_type": team_type,
                    "shift": shifts[shift_key],
                    "team_leader": leader,
                },
            )
            team.team_type = team_type
            team.shift = shifts[shift_key]
            team.team_leader = leader
            team.save()
            team.members.set([m1, m2])
            teams[name] = team

        # Prune stale demo teams (and their routes) from earlier seed runs.
        stale = Team.objects.filter(camp=camp).exclude(name__in=[s[0] for s in specs])
        Route.objects.filter(team__in=stale).delete()
        stale.delete()
        return teams

    # -- routes ------------------------------------------------------------

    def _seed_routes(self, camp, teams):
        def compound(code):
            return Compound.objects.filter(camp=camp, code=code).first()

        mapping = {
            "Grumbullimi Zona 1": ["Z1"],
            "Grumbullimi Zona 2": ["Z2"],
            "Grumbullimi Zona 3": ["Z3"],
            "Pastrimi Veri": ["PUBN"],
            "Pastrimi Jug": ["PUBS"],
        }
        for team_name, codes in mapping.items():
            team = teams.get(team_name)
            if not team:
                continue
            comps = [compound(c) for c in codes if compound(c)]
            route = Route.objects.filter(team=team).first()
            if not route:
                route = Route.objects.create(team=team, is_active=True)
            route.compounds.set(comps)

    # -- tasks -------------------------------------------------------------

    def _seed_today_tasks(self, camp):
        today = timezone.localdate()
        now = timezone.now()

        # Today's plan weekday (0=Mon..4=Fri); weekends fold onto Monday's plan.
        plan_day = today.weekday() if today.weekday() <= 4 else 0

        # Route -> team lookup per compound + team_type (one route per team).
        route_team = {}
        for route in Route.objects.filter(
            team__camp=camp, is_active=True
        ).select_related("team", "team__shift").prefetch_related("compounds"):
            for comp in route.compounds.all():
                route_team[(comp.id, route.team.team_type)] = route.team

        # Wipe today's tasks so re-seeding is deterministic.
        DailyCleaningTask.objects.filter(room__camp=camp, task_date=today).delete()

        rooms = Room.objects.filter(is_active=True, camp=camp).select_related("compound")

        # State pattern to simulate a shift in progress (per team, so each team shows
        # its own mix of collected / in-progress / awaiting).
        pattern = ["done", "done", "in_progress", "done", "planned", "done", "in_progress", "planned"]
        counts = {"total": 0, "done": 0, "in_progress": 0, "planned": 0}
        seq = {}

        for room in rooms:
            if room.service_start_date and today < room.service_start_date:
                continue
            if room.service_end_date and today > room.service_end_date:
                continue

            is_dumpster = room.space_type == "dumpster"
            # Collection is scheduled per weekday; only today's points get a task.
            if is_dumpster and room.collection_weekday != plan_day:
                continue

            team_type = "collection" if is_dumpster else "cleaning"
            team = route_team.get((room.compound_id, team_type))

            i = seq.get(team_type, 0)
            seq[team_type] = i + 1
            state = pattern[i % len(pattern)]
            # Unpaid/overdue dumpsters are "passed but not collected" -> stay planned.
            if is_dumpster and not room.can_collect:
                state = "planned"

            credit = Decimal("1.00") if is_dumpster else (room.actual_sqm or Decimal("0"))
            completed_at = now - timedelta(minutes=(i * 7) % 180) if state == "done" else None

            DailyCleaningTask.objects.create(
                room=room, task_date=today, index_in_day=1,
                task_type="regular", state=state, sla_credit_sqm=credit,
                assigned_to_team=team, shift=team.shift if team else None,
                completed_at=completed_at,
            )

            if is_dumpster:
                room.last_collected_at = completed_at if state == "done" else room.last_collected_at
                room.save(update_fields=["last_collected_at"])

            counts["total"] += 1
            if state in counts:
                counts[state] += 1

        return counts
