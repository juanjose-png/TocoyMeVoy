from api.invoice import serializers as invoice_serializers
from rest_framework import status
from rest_framework.authentication import BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView




class SaveLinkView(APIView):
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = invoice_serializers.SaveLinkSerializer

    def post(self, request, *args, **kwargs):
        """
        Save the link to the invoice file and process it.
        """
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Call the create method of the serializer
        serializer.create(serializer.validated_data)
        
        return Response(
            {"message": "Link saved successfully", "next_download_obj": serializer.data},
            status=status.HTTP_201_CREATED
        )
