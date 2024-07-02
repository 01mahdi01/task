from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers

from django.core.validators import MinLengthValidator
from .validators import number_validator, special_char_validator, letter_validator
from pdfmaker.user.models import BaseUser, Profile
from pdfmaker.api.mixins import ApiAuthMixin
from pdfmaker.user.selectors import get_profile
from pdfmaker.user.services import register, update_or_add_signature, generate_user_pdf
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from celery.result import AsyncResult
from django.http import JsonResponse
from drf_spectacular.utils import extend_schema
from django.core.cache import cache


class ProfileApi(ApiAuthMixin, APIView):
    class OutPutSerializer(serializers.ModelSerializer):
        class Meta:
            model = Profile
            fields = ("bio", "posts_count", "subscriber_count", "subscription_count")

        def to_representation(self, instance):
            rep = super().to_representation(instance)
            cache_profile = cache.get(f"profile_{instance.user}", {})
            if cache_profile:
                rep["posts_count"] = cache_profile.get("posts_count")
                rep["subscriber_count"] = cache_profile.get("subscribers_count")
                rep["subscription_count"] = cache_profile.get("subscriptions_count")

            return rep

    @extend_schema(responses=OutPutSerializer)
    def get(self, request):
        query = get_profile(user=request.user)
        return Response(self.OutPutSerializer(query, context={"request": request}).data)


class RegisterApi(APIView):
    class InputRegisterSerializer(serializers.Serializer):
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
            if BaseUser.objects.filter(email=email).exists():
                raise serializers.ValidationError("email Already Taken")
            return email

        def validate(self, data):
            if not data.get("password") or not data.get("confirm_password"):
                raise serializers.ValidationError("Please fill password and confirm password")

            if data.get("password") != data.get("confirm_password"):
                raise serializers.ValidationError("confirm password is not equal to password")
            return data

    class OutPutRegisterSerializer(serializers.ModelSerializer):

        token = serializers.SerializerMethodField("get_token")

        class Meta:
            model = BaseUser
            fields = ("name", "email", "token", "created_at", "updated_at")

        def get_token(self, user):
            data = dict()
            token_class = RefreshToken

            refresh = token_class.for_user(user)

            data["refresh"] = str(refresh)
            data["access"] = str(refresh.access_token)

            return data

    @extend_schema(request=InputRegisterSerializer, responses=OutPutRegisterSerializer)
    def post(self, request):
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
            return Response(
                f"Database Error {ex}",
                status=status.HTTP_400_BAD_REQUEST
            )
        return Response(self.OutPutRegisterSerializer(user, context={"request": request}).data)


class LoginView(APIView):
    class inputserializer(serializers.Serializer):
        email = serializers.EmailField(max_length=100)

    def post(self, request):
        serializer = self.inputserializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data.get("email")
        user = BaseUser.objects.get(email=email)
        # self.get_tokens_for_user(user)
        refresh = RefreshToken.for_user(user)

        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        })


class AddSignature(APIView):
    class InputSerializer(serializers.Serializer):
        signFile = serializers.ImageField()

    def post(self, request):
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        signature = serializer.validated_data.get("signFile")
        update_or_add_signature(signature, user)
        return Response({'message': 'Signature updated successfully'})


class StartPdfTaskView(APIView):
    class InputSerializer(serializers.Serializer):
        user_id = serializers.IntegerField()

    def post(self, request, *args, **kwargs):
        serializer = self.InputSerializer(data=request.data)
        if serializer.is_valid():
            user_id = serializer.validated_data['user_id']
            task = generate_user_pdf.delay(user_id)
            return Response({'task_id': task.id}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CheckTaskStatusView(APIView):
    class InputSerializer(serializers.Serializer):
        task_id = serializers.CharField()

    def get(self, request):
        serializer = self.InputSerializer(data=request.query_params)
        print(1)
        if serializer.is_valid():
            task_id = serializer.validated_data['task_id']
            result = AsyncResult(task_id)

            return Response(JsonResponse(result))
            redis.key
            # if result.status == 'SUCCESS':
            #     print(5)
            #     pdf_url = result.result
            #     print(6)
            #     return Response({'status': result.status, 'pdf_url': pdf_url})
            # return Response({'status': result.status}, status=status.HTTP_200_OK)
        # return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
