from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers
from config.django import base as settings
import os
from django.core.validators import MinLengthValidator
from .validators import number_validator, special_char_validator, letter_validator
from pdfmaker.user.models import BaseUser, Profile
from pdfmaker.api.mixins import ApiAuthMixin
from pdfmaker.user.selectors import get_profile
from pdfmaker.user.services import register, update_or_add_signature, generate_user_pdf, check_task_status, delete_pdf
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema
from django.core.cache import cache


class ProfileApi(ApiAuthMixin, APIView):
    """
    API view to retrieve the profile of the authenticated user.
    """

    class OutPutSerializer(serializers.ModelSerializer):
        """
        Serializer for outputting profile data.
        """

        class Meta:
            model = Profile
            fields = ("bio", "posts_count", "subscriber_count", "subscription_count")

        def to_representation(self, instance):
            """
            Customize the representation of the profile data to include cache data.
            """
            rep = super().to_representation(instance)
            cache_profile = cache.get(f"profile_{instance.user}", {})
            if cache_profile:
                rep["posts_count"] = cache_profile.get("posts_count")
                rep["subscriber_count"] = cache_profile.get("subscribers_count")
                rep["subscription_count"] = cache_profile.get("subscriptions_count")

            return rep

    @extend_schema(responses=OutPutSerializer)
    def get(self, request):
        """
        Get the profile data of the authenticated user.
        """
        query = get_profile(user=request.user)
        return Response(self.OutPutSerializer(query, context={"request": request}).data)


class RegisterApi(APIView):
    """
    API view to register a new user.
    """

    class InputRegisterSerializer(serializers.Serializer):
        """
        Serializer for validating registration data.
        """
        name = serializers.CharField(max_length=100, required=True)
        email = serializers.EmailField(max_length=255)
        bio = serializers.CharField(max_length=1000, required=False)
        password = serializers.CharField(
            validators=[
                number_validator,
                letter_validator,
                special_char_validator,
                MinLengthValidator(limit_value=10)
            ]
        )
        confirm_password = serializers.CharField(max_length=255)

        def validate_email(self, email):
            """
            Validate that the email is not already taken.
            """
            if BaseUser.objects.filter(email=email).exists():
                raise serializers.ValidationError("Email already taken.")
            return email

        def validate(self, data):
            """
            Validate that the password and confirm_password fields match.
            """
            if not data.get("password") or not data.get("confirm_password"):
                raise serializers.ValidationError("Please fill in both password and confirm password.")

            if data.get("password") != data.get("confirm_password"):
                raise serializers.ValidationError("Confirm password does not match password.")
            return data

    class OutPutRegisterSerializer(serializers.ModelSerializer):
        """
        Serializer for outputting registration data along with tokens.
        """
        token = serializers.SerializerMethodField("get_token")

        class Meta:
            model = BaseUser
            fields = ("name", "email", "token", "created_at", "updated_at")

        def get_token(self, user):
            """
            Generate access and refresh tokens for the user.
            """
            token_class = RefreshToken
            refresh = token_class.for_user(user)
            return {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            }

    @extend_schema(request=InputRegisterSerializer, responses=OutPutRegisterSerializer)
    def post(self, request):
        """
        Register a new user and return user data with tokens.
        """
        serializer = self.InputRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = register(
                name=serializer.validated_data.get("name"),
                email=serializer.validated_data.get("email"),
                password=serializer.validated_data.get("password"),
                bio=serializer.validated_data.get("bio"),
            )
        except Exception as ex:
            return Response(f"Database Error: {ex}", status=status.HTTP_400_BAD_REQUEST)
        return Response(self.OutPutRegisterSerializer(user, context={"request": request}).data)


class LoginView(APIView):
    """
    API view for user login to get authentication tokens.
    """

    class InputSerializer(serializers.Serializer):
        """
        Serializer for validating login data.
        """
        email = serializers.EmailField(max_length=100)

    def post(self, request):
        """
        Authenticate the user and return access and refresh tokens.
        """
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data.get("email")
        user = BaseUser.objects.get(email=email)
        refresh = RefreshToken.for_user(user)
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        })


class AddSignature(APIView):
    """
    API view to add or update the user's signature.
    """

    class InputSerializer(serializers.Serializer):
        """
        Serializer for validating the signature file.
        """
        signFile = serializers.ImageField()

    def post(self, request):
        """
        Update the user's signature with the provided image file.
        """
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        signature = serializer.validated_data.get("signFile")
        update_or_add_signature(signature, user)

        delete_pdf(user)

        return Response({'message': 'Signature updated successfully'})


class StartPdfTaskView(APIView):
    """
    API view to start a Celery task for generating a user PDF.
    """

    class InputSerializer(serializers.Serializer):
        """
        Serializer for validating the user ID for the PDF task.
        """
        user_id = serializers.IntegerField()
        task_id = serializers.CharField(max_length=200, default=None)

    def post(self, request, *args, **kwargs):
        """
        Start a background task to generate a PDF for the specified user.
        """
        serializer = self.InputSerializer(data=request.data)
        if serializer.is_valid():
            user_id = serializer.validated_data['user_id']
            pdf_dir = os.path.join(settings.MEDIA_ROOT, "pdfs")
            pdf_path = os.path.join(pdf_dir, f'user_{user_id}.pdf')
            if not os.path.exists(pdf_path):
                task = generate_user_pdf.delay(user_id)
                return Response({'task_id': task.id}, status=status.HTTP_200_OK)
            elif serializer.validated_data['task_id'] != "None":
                task_id = serializer.validated_data['task_id']
                result_task = check_task_status(task_id)
                return Response(result_task)


class CheckTaskStatusView(APIView):
    """
    API view to check the status of a Celery task.
    """

    # class InputSerializer(serializers.Serializer):
    #     """
    #     Serializer for validating the task ID.
    #     """
    #     task_id = serializers.CharField()
    #
    # def get(self, request):
    #     """
    #     Check the status of the specified Celery task and return the result.
    #     """
    #     serializer = self.InputSerializer(data=request.query_params)
    #     if serializer.is_valid():
    #         task_id = serializer.validated_data['task_id']
    #         result_task = check_task_status(task_id)
    #         return Response(result_task)
    #     return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
