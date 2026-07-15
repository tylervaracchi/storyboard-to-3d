// Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
// Licensed under the MIT License. See LICENSE in the repository root.
// StoryboardThumbnailLibrary.h - Content Browser thumbnail export for Python

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "StoryboardThumbnailLibrary.generated.h"

/**
 * Exposes the editor's Content Browser thumbnail pipeline to Python.
 *
 * The Python tooling generates asset thumbnails with a turntable capture
 * (core/thumbnail_generator.py); this library lets it first reuse exactly
 * what the Content Browser shows: the thumbnail cached inside the asset's
 * package, or a fresh render from the same thumbnail renderer the Content
 * Browser uses.
 */
UCLASS()
class STORYBOARDTO3D_API UStoryboardThumbnailLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    /**
     * Export an asset's Content Browser thumbnail to a PNG file.
     *
     * Tries the thumbnail cached in the asset's package first (in memory,
     * then from the package file on disk); when none exists, renders one
     * with the editor's thumbnail renderer - the same image the Content
     * Browser would produce for meshes, materials, blueprints, etc.
     *
     * @param ObjectPath  Asset path, e.g. /Game/Props/SM_Ball or
     *                    /Game/Props/SM_Ball.SM_Ball.
     * @param OutputPng   Absolute path of the PNG file to write.
     * @param MinSize     Reject thumbnails smaller than this many pixels
     *                    on either side (clamped to at least 16).
     * @return true when a valid PNG was written to OutputPng; false on any
     *         failure (never crashes or raises).
     */
    UFUNCTION(BlueprintCallable, Category = "StoryboardTo3D|Thumbnails")
    static bool ExportAssetThumbnail(const FString& ObjectPath, const FString& OutputPng, int32 MinSize = 16);
};
