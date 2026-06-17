from app.models import BenefitPackage
 
 
def list_packages(fund=None):
    qs = BenefitPackage.objects.all()
    return qs.filter(fund__iexact=fund) if fund else qs
 
 
def create_package(**data):
    return BenefitPackage.objects.create(**data)
 
 
def update_package(instance, **data):
    for key, value in data.items():
        setattr(instance, key, value)
    instance.save()
    return instance
 
 
def delete_package(instance):
    instance.delete()
 