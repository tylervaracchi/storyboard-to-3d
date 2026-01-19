// Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
// This code is proprietary. Unauthorized copying or use is prohibited.
// StoryboardPythonBridge.h - Bridge between C++ and Python

#pragma once

#include "CoreMinimal.h"
#include "Engine/EngineTypes.h"
#include "StoryboardPythonBridge.generated.h"

USTRUCT(BlueprintType)
struct FStoryboardPanel
{
    GENERATED_BODY()
    
    UPROPERTY(BlueprintReadWrite)
    FString ImagePath;
    
    UPROPERTY(BlueprintReadWrite)
    int32 Index;
    
    UPROPERTY(BlueprintReadWrite)
    FString ShotType;
    
    UPROPERTY(BlueprintReadWrite)
    int32 NumCharacters;
    
    UPROPERTY(BlueprintReadWrite)
    TArray<FString> Objects;
    
    UPROPERTY(BlueprintReadWrite)
    FString Mood;
    
    UPROPERTY(BlueprintReadWrite)
    FString TimeOfDay;
};

UCLASS(BlueprintType)
class STORYBOARDTO3D_API UStoryboardPythonBridge : public UObject
{
    GENERATED_BODY()
    
public:
    // Functions callable from Python
    
    UFUNCTION(BlueprintCallable, Category = "Storyboard")
    static void CreateSceneFromPanel(const FStoryboardPanel& Panel);
    
    UFUNCTION(BlueprintCallable, Category = "Storyboard")
    static class ULevelSequence* CreateSequenceForPanel(const FStoryboardPanel& Panel, float Duration);
    
    UFUNCTION(BlueprintCallable, Category = "Storyboard")
    static void PlaceActorInScene(const FString& AssetPath, FVector Location, FRotator Rotation);
    
    UFUNCTION(BlueprintCallable, Category = "Storyboard")
    static class ACineCameraActor* CreateCamera(FVector Location, FRotator Rotation, float FocalLength);
    
    UFUNCTION(BlueprintCallable, Category = "Storyboard")
    static void SetupLighting(const FString& Mood, const FString& TimeOfDay);
    
    UFUNCTION(BlueprintCallable, Category = "Storyboard")
    static TArray<FString> FindAssetsMatching(const FString& SearchTerm);
    
    UFUNCTION(BlueprintCallable, Category = "Storyboard")
    static void ShowNotification(const FString& Message, bool bSuccess = true);
    
    // Utility functions
    
    UFUNCTION(BlueprintCallable, Category = "Storyboard|Utils")
    static FString GetProjectContentDir();
    
    UFUNCTION(BlueprintCallable, Category = "Storyboard|Utils")
    static bool SaveTextureToFile(class UTexture2D* Texture, const FString& FilePath);
    
    UFUNCTION(BlueprintCallable, Category = "Storyboard|Utils")
    static class UTexture2D* LoadTextureFromFile(const FString& FilePath);
};
