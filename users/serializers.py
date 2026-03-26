from django.contrib.auth import get_user_model
from rest_framework import serializers
import re

from app.core.input_validation import contains_attack, sanitize_text
from users.utils.sanitize import sanitize_email
from .models import   FAQ, ContactSubmission, CustomUser, Governance, MediaResource, Member , InterventionProposal, News, NewsletterSubscription, ProposalDocument, ProposalSubmission, TemporaryFile, UserRole
from django.db.models import Q
import logging
User = get_user_model()
logger = logging.getLogger(__name__)
from django.core.validators import EmailValidator


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    position = serializers.CharField(max_length=200, required=False, allow_blank=True)
    organization = serializers.CharField(max_length=200, required=False, allow_blank=True)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)

    profile_image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = CustomUser
        fields = (
            'username', 'email', 'password', 'password_confirm',
            'first_name', 'last_name', 'country', 'profile_image',
            # Member fields
            'position', 'organization', 'phone_number', 'notes',
        )
        extra_kwargs = {
            'email': {'required': True},
            'username': {'required': True},
        }

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError("Passwords do not match.")
        return data

    def validate_email(self, value):
        if CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_username(self, value):
        if CustomUser.objects.filter(username=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def create(self, validated_data):
        # Extract member and image fields
        member_data = {
            'position': validated_data.pop('position', ''),
            'organization': validated_data.pop('organization', ''),
            'phone_number': validated_data.pop('phone_number', ''),
            'notes': validated_data.pop('notes', ''),
        }
        
        validated_data.pop('password_confirm')

        profile_image = validated_data.pop('profile_image', None)

        user = CustomUser.objects.create_user(**validated_data)
        
        if profile_image:
            user.profile_image = profile_image
            user.save()

        Member.objects.create(
            user=user,
            **member_data
        )

        return user
    
    
class VerifyUserSerializer(serializers.ModelSerializer):
    """
    Serializer for verifying a user account.
    Allows updating the `is_active` field based on secretariate approval.
    If `is_active` is set to False, the user's status remains unchanged (already inactive for pending users).
    """
    class Meta:
        model = CustomUser
        fields = ['is_active']  
        extra_kwargs = {
            'is_active': {'required': True}  
        }

    def validate_is_active(self, value):
        """
        Custom validation: If setting to False on a pending user, it remains inactive (no change needed).
        But allow explicit setting for clarity (e.g., rejection).
        """
        if not value:

            pass
        return value

    def update(self, instance, validated_data):
        """
        Override update to handle verification logic.
        - If is_active=True, activate the user.
        - If is_active=False, leave as is (already inactive).
        """
        if validated_data.get('is_active', False):
            instance.is_active = True
        else:
            # Remains the same (inactive)
            pass
        instance.save()
        return instance

class LoginSerializer(serializers.Serializer):
    username_or_email = serializers.CharField()
    password = serializers.CharField(write_only=True)
    
    
    def validate_username_or_email(self, value):
        """
        Sanitize and validate username/email input.
        """

        value = value.strip()

        if not value:
            raise serializers.ValidationError("This field cannot be empty.")

        if "@" in value:
            validator = EmailValidator()
            try:
                validator(value)
            except Exception:
                raise serializers.ValidationError("Enter a valid email address.")

        return value.lower()

    def validate(self, data):
        username_or_email = data.get('username_or_email')
        password = data.get('password')

        user = CustomUser.objects.filter(
            Q(username=username_or_email) | Q(email=username_or_email)
        ).first()
        
        if not user:
            raise serializers.ValidationError("Invalid username or email.")
        
        if user.is_blocked:
            raise serializers.ValidationError("Your account has been blocked. Please contact support.")
        
        # Verify password
        if not user.check_password(password):
            raise serializers.ValidationError("Invalid password. Please check your password and try again.")

        if not user.is_active:
            raise serializers.ValidationError("Your account is inactive. Please contact support.")

        return {"user": user}


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 
                 'profile_image', 'country', 'is_email_verified', 'status','role')
        read_only_fields = ('id', 'is_email_verified', 'status')


class MemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = Member
        fields = '__all__'
        
        

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        phone = representation.get('phone_number')
        if phone and len(phone) > 4:
            first = phone[:2]
            last = phone[-2:]
            representation['phone_number'] = f"{first}{'*' * (len(phone) - 4)}{last}"

        user_data = representation.get('user')
        if user_data:
            email = user_data.get('email')
            if email:
                parts = email.split('@')
                if len(parts) == 2:
                    name, domain = parts
                    if len(name) > 4:
                        name_obfuscated = f"{name[:2]}{'*' * (len(name) - 4)}{name[-2:]}"
                    else:
                        name_obfuscated = f"{name[0]}{'*' * (len(name) - 2)}{name[-1]}"
                    representation['user']['email'] = f"{name_obfuscated}@{domain}"

        return representation

class UserMeSerializer(serializers.ModelSerializer):
    groups = serializers.SlugRelatedField(
        many=True, slug_field="name", read_only=True
    )
    user_permissions = serializers.SlugRelatedField(
        many=True, slug_field="codename", read_only=True
    )
    member = MemberSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'groups',
            'user_permissions',
            'country',
            'is_active',
            'is_staff',
            'is_superuser',
            'is_email_verified',
            'status',
            'is_blocked',
            'last_login',
            'role',
            'member'
        ]
        read_only_fields = [
            'id',
            'date_joined',
            'last_login',
            'is_staff',
            'is_superuser'
        ]
        
    def to_representation(self, instance):
        """
        Override to handle cases where user might not have a member profile
        """
        data = super().to_representation(instance)
        
        if not data.get('member'):
            data['member'] = {
                'id': None,
                'position': None,
                'organization': None,
                'phone_number': None,
                'notes': None,
                'created_at': None,
                'is_profile_complete': False
            }
        
        return data
     
     
# class ProposalDocumentSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = ProposalDocument
#         fields = ['document', 'original_name', 'is_public']   
        
# class InterventionProposalSerializer(serializers.ModelSerializer):
#     uploaded_documents = serializers.ListField(
#         child=serializers.FileField(max_length=255, allow_empty_file=False),
#         write_only=True,
#         required=False
#     )
#     uploadedDocument = serializers.FileField(
#         max_length=255, allow_empty_file=False, write_only=True, required=False
#     )

#     class Meta:
#         model = InterventionProposal
#         fields = [
#             'name', 'phone', 'email', 'profession', 'organization', 'county',
#             'intervention_name', 'intervention_type', 'beneficiary',
#             'justification', 'expected_impact', 'additional_info','reference_number',
#             'signature', 'date', 'uploaded_documents', 'uploadedDocument', 'is_public'
#         ]

#     def create(self, validated_data):
#         uploaded_documents = validated_data.pop('uploaded_documents', [])
#         uploaded_document = validated_data.pop('uploadedDocument', None)
        
#         if uploaded_document:
#             uploaded_documents.append(uploaded_document)
        
#         proposal = InterventionProposal.objects.create(**validated_data)
        
#         for document in uploaded_documents:
#             logger.info(f"Saving document: {document.name}")
#             ProposalDocument.objects.create(
#                 proposal=proposal,
#                 document=document,
#                 original_name=document.name,
#                 is_public=proposal.is_public
#             )
        
#         logger.info(f"Proposal {proposal.id} created with {proposal.documents.count()} documents")
#         return proposal


class ProposalDocumentSerializer(serializers.ModelSerializer):
    document_url = serializers.SerializerMethodField()
    
    class Meta:
        model = ProposalDocument
        fields = ['id', 'document', 'document_url', 'original_name', 'is_public']
    
    def get_document_url(self, obj):
        request = self.context.get('request')
        if obj.document and hasattr(obj.document, 'url'):
            if request:
                return request.build_absolute_uri(obj.document.url)
            return obj.document.url
        return None


def _mask(value: str) -> str:
    """
    Masks a string: keeps first and last char, replaces middle with ********.
    """
    if not value or len(value) <= 2:
        return value
    return f"{value[0]}{'*' * (len(value) - 2)}{value[-1]}"


MASKED_FIELDS = ["name", "phone", "email", "county", "signature"]

# class InterventionProposalSerializer(serializers.ModelSerializer):
#     uploaded_documents = serializers.ListField(
#         child=serializers.FileField(max_length=255, allow_empty_file=False),
#         write_only=True,
#         required=False
#     )
#     uploadedDocument = serializers.FileField(
#         max_length=255, allow_empty_file=False, write_only=True, required=False
#     )
#     interventionName = serializers.CharField(
#         source='intervention_name',
#         required=False,
#         allow_blank=True,
#         allow_null=True
#     )
#     interventionType = serializers.CharField(
#         source='intervention_type',
#         required=False,
#         allow_blank=True,
#         allow_null=True
#     )
#     documents = ProposalDocumentSerializer(many=True, read_only=True)

#     class Meta:
#         model = InterventionProposal
#         fields = [
#             'id',
#             'name', 'phone', 'email', 'profession', 'organization', 'county',
#             'intervention_name', 'intervention_type', 'beneficiary',
#             'justification', 'expected_impact', 'additional_info', 'reference_number',
#             'signature', 'date', 'uploaded_documents', 'uploadedDocument', 'is_public',
#             'interventionName', 'interventionType', 'rescore_open',
#             'documents'
#         ]
#         read_only_fields = ['id', 'reference_number','rescore_open', 'documents']

#     def to_representation(self, instance):
#         data = super().to_representation(instance)
#         for field in MASKED_FIELDS:
#             if field in data and data[field]:
#                 data[field] = _mask(str(data[field]))
#         return data

#     def create(self, validated_data):
#         validated_data.pop('interventionName', None)
#         validated_data.pop('interventionType', None)

#         uploaded_documents = validated_data.pop('uploaded_documents', [])
#         uploaded_document = validated_data.pop('uploadedDocument', None)

#         if uploaded_document:
#             uploaded_documents.append(uploaded_document)

#         proposal = InterventionProposal.objects.create(**validated_data)

#         for document in uploaded_documents:
#             logger.info(f"Saving document: {document.name}")
#             ProposalDocument.objects.create(
#                 proposal=proposal,
#                 document=document,
#                 original_name=document.name,
#                 is_public=proposal.is_public
#             )

#         logger.info(f"Proposal {proposal.id} created with {proposal.documents.count()} documents")
#         return proposal

SAFE_TEXT_FIELDS = [
    "name",
    "profession",
    "organization",
    "county",
    "intervention_name",
    "intervention_type",
    "beneficiary",
    "justification",
    "expected_impact",
    "additional_info",
    "signature",
]


ALLOWED_FILE_TYPES = [".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg"]
MAX_FILE_SIZE_MB = 10


class InterventionProposalSerializer(serializers.ModelSerializer):

    uploaded_documents = serializers.ListField(
        child=serializers.FileField(max_length=255, allow_empty_file=False),
        write_only=True,
        required=False
    )

    uploadedDocument = serializers.FileField(
        max_length=255,
        allow_empty_file=False,
        write_only=True,
        required=False
    )

    interventionName = serializers.CharField(
        source='intervention_name',
        required=False,
        allow_blank=True,
        allow_null=True
    )

    interventionType = serializers.CharField(
        source='intervention_type',
        required=False,
        allow_blank=True,
        allow_null=True
    )

    documents = ProposalDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = InterventionProposal
        fields = [
            'id',
            'name', 'phone', 'email', 'profession', 'organization', 'county',
            'intervention_name', 'intervention_type', 'beneficiary',
            'justification', 'expected_impact', 'additional_info',
            'reference_number',
            'signature', 'date',
            'uploaded_documents', 'uploadedDocument',
            'is_public',
            'interventionName', 'interventionType',
            'rescore_open',
            'documents'
        ]

        read_only_fields = ['id', 'reference_number', 'rescore_open', 'documents']


    def validate_name(self, value):
        value = sanitize_text(value)

        if not re.match(r"^[A-Za-z\s\-\.'’]{2,100}$", value):
            raise serializers.ValidationError("Invalid name.")

        return value

    def validate_phone(self, value):
        value = sanitize_text(value)

        if not re.match(r"^\+?[0-9]{7,15}$", value):
            raise serializers.ValidationError("Invalid phone number.")

        return value

    def validate_email(self, value):
        if value:
            return value.lower().strip()
        return value
    
    def validate_uploaded_documents(self, files):
        for file in files:
            self._validate_file(file)
        return files

    def validate_uploadedDocument(self, file):
        self._validate_file(file)
        return file

    def _validate_file(self, file):

        # size check
        if file.size > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise serializers.ValidationError("File too large (max 10MB).")

        ext = file.name.lower().rsplit(".", 1)[-1]
        if f".{ext}" not in ALLOWED_FILE_TYPES:
            raise serializers.ValidationError("Unsupported file type.")

        file.name = sanitize_text(file.name)

    def validate(self, attrs):

        for field in SAFE_TEXT_FIELDS:
            if field in attrs and attrs[field]:
                cleaned = sanitize_text(attrs[field])

                if contains_attack(cleaned):
                    raise serializers.ValidationError(
                        {field: "Suspicious input detected."}
                    )

                attrs[field] = cleaned

        return attrs


    def to_representation(self, instance):
        data = super().to_representation(instance)

        for field in MASKED_FIELDS:
            if field in data and data[field]:
                data[field] = _mask(str(data[field]))

        return data


    def create(self, validated_data):

        request = self.context.get("request")

        validated_data.pop('interventionName', None)
        validated_data.pop('interventionType', None)

        uploaded_documents = validated_data.pop('uploaded_documents', [])
        uploaded_document = validated_data.pop('uploadedDocument', None)

        if uploaded_document:
            uploaded_documents.append(uploaded_document)

        if request:
            validated_data["ip_address"] = self._get_client_ip(request)
            validated_data["user_agent"] = request.META.get("HTTP_USER_AGENT", "")[:500]

        proposal = InterventionProposal.objects.create(**validated_data)

        for document in uploaded_documents:
            ProposalDocument.objects.create(
                proposal=proposal,
                document=document,
                original_name=document.name,
                is_public=proposal.is_public
            )

        logger.info(
            f"Proposal {proposal.id} created with {proposal.documents.count()} documents"
        )

        return proposal

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")

class ProposalSubmissionSerializer(serializers.ModelSerializer):
    temp_files = serializers.SerializerMethodField()
    
    class Meta:
        model = ProposalSubmission
        fields = '__all__'
        read_only_fields = ('submission_id', 'task_id', 'attempts', 'processing_started_at', 'completed_at')
    
    def get_temp_files(self, obj):
        return obj.temp_files.count()

class TemporaryFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemporaryFile
        fields = '__all__'
        
        
        
        
        
class MemberListSerializer(serializers.ModelSerializer):
    # User fields
    username = serializers.CharField(source='user.username', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    is_active = serializers.BooleanField(source='user.is_active', read_only=True)
    last_login = serializers.DateTimeField(source='user.last_login', read_only=True)
    created_at = serializers.DateTimeField(source='user.date_joined', read_only=True)
    profile_image = serializers.ImageField(source='user.profile_image', read_only=True)
    role = serializers.CharField(source='user.role', read_only=True) 
    
    # Member fields
    phone_number = serializers.CharField(read_only=True)
    notes = serializers.CharField(read_only=True)
    organization = serializers.CharField(read_only=True)

    class Meta:
        model = Member
        fields = [
            'id',
            'username',
            'first_name', 
            'last_name',
            'email',
            'is_active',
            'last_login',
            'created_at',
            'profile_image',
            'phone_number',
            'notes',
            'organization',
            'role',  
        ]


    def to_representation(self, instance):
        representation = super().to_representation(instance)

        phone = representation.get('phone_number')
        if phone and len(phone) > 4:
            first = phone[:2]
            last = phone[-2:]
            representation['phone_number'] = f"{first}{'*' * (len(phone) - 4)}{last}"

        # Obfuscate email
        email = representation.get('email')
        if email:
            parts = email.split('@')
            if len(parts) == 2:
                name, domain = parts
                if len(name) > 4:
                    name_obfuscated = f"{name[:2]}{'*' * (len(name) - 4)}{name[-2:]}"
                elif len(name) > 2:
                    name_obfuscated = f"{name[0]}{'*' * (len(name) - 2)}{name[-1]}"
                else:
                    name_obfuscated = '*' * len(name)
                representation['email'] = f"{name_obfuscated}@{domain}"

        return representation


class MemberAdminSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=UserRole.CHOICES, source='user.role')
    phone_number = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    organization = serializers.CharField(required=False)

    class Meta:
        model = Member
        fields = ['phone_number', 'notes', 'organization', 'role']

    def update(self, instance, validated_data):
        user_data = validated_data.pop('user', {})

        # Update Member fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update User fields
        if user_data:
            user = instance.user
            for attr, value in user_data.items():
                setattr(user, attr, value)
            user.save()

        return instance


class FAQSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = '__all__'


class GovernanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Governance
        fields = '__all__'
    
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        
        # Fix image URL if it exists
        if representation.get('image') and representation['image'].startswith('http://localhost'):
            representation['image'] = representation['image'].replace(
                'http://localhost', 
                'https://bptap.health.go.ke'
            )
        
        return representation


class NewsSerializer(serializers.ModelSerializer):
    tags_list = serializers.ReadOnlyField(source='get_tags_list')
    
    class Meta:
        model = News
        fields = '__all__'
    
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        
        if representation.get('image') and representation['image'].startswith('http://localhost'):
            representation['image'] = representation['image'].replace(
                'http://localhost', 
                'https://bptap.health.go.ke'
            )
        
        return representation

class MediaResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = MediaResource
        fields = '__all__'
        

class ContactSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactSubmission
        fields = '__all__'
        read_only_fields = ['ip_address', 'created_at']

    def validate_full_name(self, value):
        value = sanitize_text(value, 50)
        if not value:
            raise serializers.ValidationError("Full name is required.")
        return value

    def validate_email(self, value):
        value = sanitize_email(value)
        if not value:
            raise serializers.ValidationError("Email is required.")
        return value

    def validate_organization(self, value):
        return sanitize_text(value, 50)

    def validate_subject(self, value):
        value = sanitize_text(value, 100)
        if not value:
            raise serializers.ValidationError("Subject is required.")
        return value

    def validate_message(self, value):
        value = sanitize_text(value, 2000)
        if not value:
            raise serializers.ValidationError("Message is required.")
        return value

class NewsletterSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsletterSubscription
        fields = ['id', 'email', 'is_active', 'subscribed_at']
        read_only_fields = ['id', 'is_active', 'subscribed_at']

    def validate_email(self, value):
        value = sanitize_email(value)
        if not value:
            raise serializers.ValidationError("Email is required.")
        return value
    
class NewsletterUnsubscribeSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)