from django.core.exceptions import ValidationError

from app.models import NationalProgram, NationalProgramProposal



def validate_program_data(program, data):
    """Check a proposal's dynamic `data` against its program's field_schema.
    Required fields present + no unknown keys (keeps each program's rows clean)."""
    data = data or {}
    errors, allowed = {}, set()
    for f in program.field_schema or []:
        key = f.get("key")
        if not key:
            continue
        allowed.add(key)
        if f.get("required") and not data.get(key):
            errors[key] = "This field is required."
    unknown = set(data) - allowed
    if unknown:
        errors["__unknown__"] = "Unexpected fields: " + ", ".join(sorted(unknown))
    if errors:
        raise ValidationError(errors)


class NationalProgramService:
    @staticmethod
    def queryset(active_only=False):
        qs = NationalProgram.objects.all()
        return qs.filter(is_active=True) if active_only else qs


class ProgramProposalService:
    @staticmethod
    def queryset(program=None):
        """Proposals, FKs pre-joined. `program` may be a numeric id or a code."""
        qs = NationalProgramProposal.objects.select_related("program", "created_by")
        if program:
            key = "program_id" if str(program).isdigit() else "program__code"
            qs = qs.filter(**{key: program})
        return qs

    @staticmethod
    def create(*, program, title, data=None, justification=None, submitted_date=None, user=None):
        validate_program_data(program, data)
        proposal = NationalProgramProposal(
            program=program,
            title=title,
            data=data or {},
            created_by=user if (user and user.is_authenticated) else None,
        )
        if submitted_date:
            proposal.submitted_date = submitted_date
        proposal.save()  # generates reference_number
        return proposal

    @staticmethod
    def update(proposal, *, title=None, justification=None, data=None, submitted_date=None):
        fields = []
        if data is not None:
            validate_program_data(proposal.program, data)
            proposal.data, _ = data, fields.append("data")
        if title is not None:
            proposal.title, _ = title, fields.append("title")
        if justification is not None:
            proposal.justification, _ = justification, fields.append("justification")
        if submitted_date is not None:
            proposal.submitted_date, _ = submitted_date, fields.append("submitted_date")
        if fields:
            fields.append("updated_at")
            proposal.save(update_fields=fields)  # ref untouched, only changed cols written
        return proposal