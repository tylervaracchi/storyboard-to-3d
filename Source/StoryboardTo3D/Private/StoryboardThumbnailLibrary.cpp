// Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
// Licensed under the MIT License. See LICENSE in the repository root.
// StoryboardThumbnailLibrary.cpp - Content Browser thumbnail export

#include "StoryboardThumbnailLibrary.h"
#include "StoryboardTo3D.h"

#if WITH_EDITOR
#include "ObjectTools.h"
#include "Misc/ObjectThumbnail.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/PackageName.h"
#include "UObject/Package.h"
#include "UObject/UObjectGlobals.h"
#include "Modules/ModuleManager.h"
#include "IImageWrapper.h"
#include "IImageWrapperModule.h"

namespace
{
    /** Write an FObjectThumbnail's uncompressed BGRA8 data to a PNG file. */
    bool SaveThumbnailAsPng(const FObjectThumbnail& Thumbnail, const FString& OutputPng, int32 MinSize)
    {
        const int32 Width = Thumbnail.GetImageWidth();
        const int32 Height = Thumbnail.GetImageHeight();
        if (Width < MinSize || Height < MinSize)
        {
            UE_LOG(LogStoryboardTo3D, Log,
                TEXT("Thumbnail %dx%d is below the minimum size %d"), Width, Height, MinSize);
            return false;
        }

        // Decompresses on demand (package thumbnails are stored compressed)
        const TArray<uint8>& RawData = Thumbnail.GetUncompressedImageData();
        const int64 ExpectedBytes = static_cast<int64>(Width) * Height * 4;
        if (RawData.Num() < ExpectedBytes)
        {
            UE_LOG(LogStoryboardTo3D, Warning,
                TEXT("Thumbnail pixel data is incomplete (%d bytes for %dx%d)"),
                RawData.Num(), Width, Height);
            return false;
        }

        IImageWrapperModule& ImageWrapperModule =
            FModuleManager::LoadModuleChecked<IImageWrapperModule>(FName("ImageWrapper"));
        TSharedPtr<IImageWrapper> PngWrapper = ImageWrapperModule.CreateImageWrapper(EImageFormat::PNG);
        if (!PngWrapper.IsValid() ||
            !PngWrapper->SetRaw(RawData.GetData(), ExpectedBytes, Width, Height, ERGBFormat::BGRA, 8))
        {
            UE_LOG(LogStoryboardTo3D, Warning, TEXT("Could not encode thumbnail pixels as PNG"));
            return false;
        }

        const TArray64<uint8> PngBytes = PngWrapper->GetCompressed(100);
        if (PngBytes.Num() == 0)
        {
            UE_LOG(LogStoryboardTo3D, Warning, TEXT("PNG compression produced no data"));
            return false;
        }

        if (!FFileHelper::SaveArrayToFile(PngBytes, *OutputPng))
        {
            UE_LOG(LogStoryboardTo3D, Warning, TEXT("Could not write PNG to %s"), *OutputPng);
            return false;
        }

        UE_LOG(LogStoryboardTo3D, Log, TEXT("Exported %dx%d thumbnail to %s"), Width, Height, *OutputPng);
        return true;
    }
}
#endif // WITH_EDITOR

bool UStoryboardThumbnailLibrary::ExportAssetThumbnail(const FString& ObjectPath, const FString& OutputPng, int32 MinSize)
{
#if WITH_EDITOR
    if (ObjectPath.IsEmpty() || OutputPng.IsEmpty())
    {
        UE_LOG(LogStoryboardTo3D, Warning, TEXT("ExportAssetThumbnail: empty object path or output path"));
        return false;
    }

    const int32 EffectiveMinSize = FMath::Max(MinSize, 16);

    // Accept both /Game/Foo/SM_Bar and /Game/Foo/SM_Bar.SM_Bar
    FString NormalizedPath = ObjectPath;
    if (!NormalizedPath.Contains(TEXT(".")))
    {
        const FString AssetName = FPackageName::GetShortName(NormalizedPath);
        NormalizedPath = FString::Printf(TEXT("%s.%s"), *NormalizedPath, *AssetName);
    }

    UObject* Asset = LoadObject<UObject>(nullptr, *NormalizedPath);
    if (!Asset)
    {
        UE_LOG(LogStoryboardTo3D, Warning,
            TEXT("ExportAssetThumbnail: could not load asset %s"), *NormalizedPath);
        return false;
    }

    // 1) The thumbnail the Content Browser already has: the in-memory
    //    package thumbnail map, then the thumbnails serialized in the
    //    package file on disk (ConditionallyLoadThumbnailsForObjects
    //    covers both).
    const FName ObjectFullName(*Asset->GetFullName());
    FThumbnailMap ThumbnailMap;
    TArray<FName> ObjectFullNames;
    ObjectFullNames.Add(ObjectFullName);
    ThumbnailTools::ConditionallyLoadThumbnailsForObjects(ObjectFullNames, ThumbnailMap);

    const FObjectThumbnail* CachedThumbnail = ThumbnailMap.Find(ObjectFullName);
    if (!CachedThumbnail)
    {
        CachedThumbnail = ThumbnailTools::GetThumbnailForObject(Asset);
    }
    if (CachedThumbnail && !CachedThumbnail->IsEmpty() &&
        CachedThumbnail->GetImageWidth() >= EffectiveMinSize &&
        CachedThumbnail->GetImageHeight() >= EffectiveMinSize)
    {
        if (SaveThumbnailAsPng(*CachedThumbnail, OutputPng, EffectiveMinSize))
        {
            return true;
        }
        UE_LOG(LogStoryboardTo3D, Log,
            TEXT("Cached thumbnail export failed for %s; rendering a fresh one"), *NormalizedPath);
    }

    // 2) No usable cached thumbnail: render one with the editor's thumbnail
    //    renderer - exactly what the Content Browser generates for meshes,
    //    materials, blueprints, and other visual assets.
    const FObjectThumbnail* GeneratedThumbnail = ThumbnailTools::GenerateThumbnailForObjectToSaveToDisk(Asset);
    if (GeneratedThumbnail && !GeneratedThumbnail->IsEmpty())
    {
        return SaveThumbnailAsPng(*GeneratedThumbnail, OutputPng, EffectiveMinSize);
    }

    UE_LOG(LogStoryboardTo3D, Log,
        TEXT("ExportAssetThumbnail: no cached or renderable thumbnail for %s"), *NormalizedPath);
    return false;
#else
    return false;
#endif // WITH_EDITOR
}
