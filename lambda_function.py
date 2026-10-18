
import os
import json
import uuid
import boto3
from urllib.parse import unquote_plus
from botocore.exceptions import ClientError
from PIL import Image

# Destination bucket for pixelated images
processed_bucket = os.environ['processed_bucket']

# S3 client
s3_client = boto3.client('s3')


def lambda_handler(event, context):
    print("Received event:", json.dumps(event))

    try:
        # Get source bucket and image key from S3 event
        source_bucket = event['Records'][0]['s3']['bucket']['name']
        key = unquote_plus(event['Records'][0]['s3']['object']['key'])

        # Prevent processing files from the destination bucket
        if source_bucket == processed_bucket:
            print("Skipping object from processed bucket.")
            return {
                'statusCode': 200,
                'body': json.dumps('Skipped processed bucket object.')
            }

        # Create a unique temporary filename
        filename = os.path.basename(key)
        object_key = str(uuid.uuid4()) + '-' + filename
        img_download_path = '/tmp/' + object_key

        # Download original image from S3
        try:
            s3_client.download_file(
                source_bucket,
                key,
                img_download_path
            )
        except ClientError as e:
            print(f"Error downloading {key}: {str(e)}")
            return {
                'statusCode': 500,
                'body': json.dumps('Failed to download source image.')
            }

        # Generate pixelated versions
        resolutions = [8, 16, 32, 48, 64]
        output_files = []

        try:
            with Image.open(img_download_path) as img:
                # Convert unsupported modes for JPEG-compatible output
                if img.mode not in ('RGB', 'RGBA'):
                    img = img.convert('RGB')

                original_size = img.size

                for size in resolutions:
                    small_img = img.resize(
                        (size, size),
                        Image.Resampling.BILINEAR
                    )

                    pixelated_img = small_img.resize(
                        original_size,
                        Image.Resampling.NEAREST
                    )

                    output_path = f'/tmp/pixelated-{size}x{size}-{object_key}'
                    pixelated_img.save(output_path, format='JPEG')
                    output_files.append((output_path, size))

        except Exception as e:
            print(f"Error pixelating image: {str(e)}")
            return {
                'statusCode': 500,
                'body': json.dumps('Failed to pixelate image.')
            }

        # Upload all pixelated images
        try:
            for output_path, size in output_files:
                output_key = f'pixelated-{size}x{size}-{key}'

                s3_client.upload_file(
                    output_path,
                    processed_bucket,
                    output_key,
                    ExtraArgs={'ContentType': 'image/jpeg'}
                )

                print(f"Uploaded: s3://{processed_bucket}/{output_key}")

        except ClientError as e:
            print(f"Error uploading pixelated image: {str(e)}")
            return {
                'statusCode': 500,
                'body': json.dumps('Failed to upload processed images.')
            }

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Successfully processed and uploaded pixelated images.',
                'source_bucket': source_bucket,
                'source_key': key,
                'destination_bucket': processed_bucket,
                'images_created': len(output_files)
            })
        }

    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps('Unexpected processing error.')
        }


def pixelate(pixelsize, image_path, pixelated_img_path):
    """Create a pixelated version of an image."""
    with Image.open(image_path) as img:
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')

        small_img = img.resize(
            pixelsize,
            Image.Resampling.BILINEAR
        )

        result = small_img.resize(
            img.size,
            Image.Resampling.NEAREST
        )

        result.save(pixelated_img_path, format='JPEG')
