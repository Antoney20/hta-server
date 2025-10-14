from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import   FAQ, ContactSubmission, CustomUser, Governance, MediaResource, Member , InterventionProposal, News, NewsletterSubscription, ProposalDocument, ProposalSubmission, TemporaryFile
from django.db.models import Q
import logging
User = get_user_model()
logger = logging.getLogger(__name__)


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    # Member profile fields
    position = serializers.CharField(max_length=200, required=False, allow_blank=True)
    organization = serializers.CharField(max_length=200, required=False, allow_blank=True)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)

    # Add profile_image field
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

class LoginSerializer(serializers.Serializer):
    username_or_email = serializers.CharField()
    password = serializers.CharField(write_only=True)

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

        # Check if user is active
        if not user.is_active:
            raise serializers.ValidationError("Your account is inactive. Please contact support.")

        return {"user": user}


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 
                 'profile_image', 'country', 'is_email_verified', 'status')
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

        # Obfuscate email if available in user
        user_data = representation.get('user')
        if user_data:
            email = user_data.get('email')
            if email:
                # Split into name and domain
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


class InterventionProposalSerializer(serializers.ModelSerializer):
    uploaded_documents = serializers.ListField(
        child=serializers.FileField(max_length=255, allow_empty_file=False),
        write_only=True,
        required=False
    )
    uploadedDocument = serializers.FileField(
        max_length=255, allow_empty_file=False, write_only=True, required=False
    )
    
    # Add these fields to handle camelCase from frontend
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
    
    # Add this to properly serialize documents
    documents = ProposalDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = InterventionProposal
        fields = [
            'id',
            'name', 'phone', 'email', 'profession', 'organization', 'county',
            'intervention_name', 'intervention_type', 'beneficiary',
            'justification', 'expected_impact', 'additional_info', 'reference_number',
            'signature', 'date', 'uploaded_documents', 'uploadedDocument', 'is_public',
            'interventionName', 'interventionType',
            'documents'  
        ]
        read_only_fields = ['id', 'reference_number', 'documents']

    def create(self, validated_data):
        # Remove camelCase fields from validated_data
        validated_data.pop('interventionName', None)
        validated_data.pop('interventionType', None)
        
        uploaded_documents = validated_data.pop('uploaded_documents', [])
        uploaded_document = validated_data.pop('uploadedDocument', None)
        
        if uploaded_document:
            uploaded_documents.append(uploaded_document)
        
        proposal = InterventionProposal.objects.create(**validated_data)
        
        for document in uploaded_documents:
            logger.info(f"Saving document: {document.name}")
            ProposalDocument.objects.create(
                proposal=proposal,
                document=document,
                original_name=document.name,
                is_public=proposal.is_public
            )
        
        logger.info(f"Proposal {proposal.id} created with {proposal.documents.count()} documents")
        return proposal

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



class FAQSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = '__all__'

class NewsSerializer(serializers.ModelSerializer):
    tags_list = serializers.ReadOnlyField(source='get_tags_list')
    
    class Meta:
        model = News
        fields = '__all__'

class GovernanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Governance
        fields = '__all__'

class MediaResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = MediaResource
        fields = '__all__'
        

class ContactSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactSubmission
        fields = '__all__'
        read_only_fields = ['ip_address', 'created_at']
        
class NewsletterSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsletterSubscription
        fields = ['id', 'email', 'is_active', 'subscribed_at']
        read_only_fields = ['id', 'is_active', 'subscribed_at']


class NewsletterUnsubscribeSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)