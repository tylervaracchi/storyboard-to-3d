// Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
// This code is proprietary. Unauthorized copying or use is prohibited.
// StoryboardPythonBridge.cpp - Implementation of bridge functions

#include "StoryboardPythonBridge.h"
#include "StoryboardTo3D.h"
#include "Engine/World.h"
#include "Engine/Engine.h"
#include "Editor/EditorEngine.h"
#include "Editor.h"
#include "LevelSequence.h"
#include "MovieScene.h"
#include "MovieSceneSequence.h"
#include "CineCameraActor.h"
#include "CineCameraComponent.h"
#include "Engine/DirectionalLight.h"
#include "Engine/PointLight.h"
#include "Components/LightComponent.h"
#include "Components/PointLightComponent.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "AssetRegistry/AssetData.h"
#include "UObject/ConstructorHelpers.h"
#include "Framework/Notifications/NotificationManager.h"
#include "Widgets/Notifications/SNotificationList.h"
#include "EditorLevelLibrary.h"
#include "EditorAssetLibrary.h"
#include "LevelSequenceActor.h"
#include "IImageWrapper.h"
#include "IImageWrapperModule.h"
#include "Misc/FileHelper.h"
#include "Engine/Texture2D.h"

void UStoryboardPythonBridge::CreateSceneFromPanel(const FStoryboardPanel& Panel)
{
    UWorld* World = GEditor->GetEditorWorldContext().World();
    if (!World)
    {
        UE_LOG(LogStoryboardTo3D, Error, TEXT("No world available"));
        return;
    }
    
    UE_LOG(LogStoryboardTo3D, Log, TEXT("Creating scene for panel %d"), Panel.Index);
    
    // Clear area for new scene
    FVector SceneCenter = FVector(Panel.Index * 2000.0f, 0, 0);
    
    // Place characters
    for (int32 i = 0; i < Panel.NumCharacters; i++)
    {
        FVector CharLocation = SceneCenter + FVector(0, i * 150.0f - (Panel.NumCharacters - 1) * 75.0f, 0);
        PlaceActorInScene(TEXT("/Engine/BasicShapes/Cylinder"), CharLocation, FRotator::ZeroRotator);
    }
    
    // Place objects
    for (const FString& ObjectName : Panel.Objects)
    {
        // Simple placement logic
        FVector ObjectLocation = SceneCenter + FVector(FMath::RandRange(-500, 500), FMath::RandRange(-500, 500), 0);
        PlaceActorInScene(TEXT("/Engine/BasicShapes/Cube"), ObjectLocation, FRotator::ZeroRotator);
    }
    
    // Setup camera based on shot type
    float CameraDistance = 500.0f;
    if (Panel.ShotType == TEXT("close"))
        CameraDistance = 200.0f;
    else if (Panel.ShotType == TEXT("wide"))
        CameraDistance = 1000.0f;
    
    FVector CameraLocation = SceneCenter + FVector(-CameraDistance, 0, 160);
    FRotator CameraRotation = (SceneCenter - CameraLocation).Rotation();
    CreateCamera(CameraLocation, CameraRotation, 50.0f);
    
    // Setup lighting
    SetupLighting(Panel.Mood, Panel.TimeOfDay);
}

ULevelSequence* UStoryboardPythonBridge::CreateSequenceForPanel(const FStoryboardPanel& Panel, float Duration)
{
    // Create a new level sequence
    FString SequenceName = FString::Printf(TEXT("Panel_%02d_Sequence"), Panel.Index);
    FString PackagePath = TEXT("/Game/StoryboardSequences/") + SequenceName;
    
    UPackage* Package = CreatePackage(*PackagePath);
    ULevelSequence* NewSequence = NewObject<ULevelSequence>(Package, *SequenceName, RF_Public | RF_Standalone);
    
    if (NewSequence)
    {
        // Setup sequence duration
        UMovieScene* MovieScene = NewSequence->GetMovieScene();
        if (MovieScene)
        {
            FFrameRate FrameRate = MovieScene->GetDisplayRate();
            int32 DurationInFrames = FMath::RoundToInt(Duration * FrameRate.AsDecimal());
            MovieScene->SetPlaybackRange(0, DurationInFrames);
        }
        
        // Save the sequence
        UEditorAssetLibrary::SaveAsset(PackagePath);
        
        UE_LOG(LogStoryboardTo3D, Log, TEXT("Created sequence: %s"), *SequenceName);
    }
    
    return NewSequence;
}

void UStoryboardPythonBridge::PlaceActorInScene(const FString& AssetPath, FVector Location, FRotator Rotation)
{
    UObject* Asset = UEditorAssetLibrary::LoadAsset(AssetPath);
    if (!Asset)
    {
        UE_LOG(LogStoryboardTo3D, Warning, TEXT("Failed to load asset: %s"), *AssetPath);
        return;
    }
    
    // Note: This is deprecated but still works in UE 5.6
    AActor* SpawnedActor = UEditorLevelLibrary::SpawnActorFromObject(Asset, Location, Rotation);
    
    if (SpawnedActor)
    {
        SpawnedActor->Tags.Add(TEXT("StoryboardGenerated"));
        UE_LOG(LogStoryboardTo3D, Log, TEXT("Placed actor at %s"), *Location.ToString());
    }
}

ACineCameraActor* UStoryboardPythonBridge::CreateCamera(FVector Location, FRotator Rotation, float FocalLength)
{
    UWorld* World = GEditor->GetEditorWorldContext().World();
    if (!World)
        return nullptr;
    
    ACineCameraActor* CameraActor = World->SpawnActor<ACineCameraActor>(Location, Rotation);
    if (CameraActor)
    {
        UCineCameraComponent* CameraComponent = CameraActor->GetCineCameraComponent();
        if (CameraComponent)
        {
            CameraComponent->CurrentFocalLength = FocalLength;
        }
        
        CameraActor->Tags.Add(TEXT("StoryboardCamera"));
        UE_LOG(LogStoryboardTo3D, Log, TEXT("Created camera with focal length %f"), FocalLength);
    }
    
    return CameraActor;
}

void UStoryboardPythonBridge::SetupLighting(const FString& Mood, const FString& TimeOfDay)
{
    UWorld* World = GEditor->GetEditorWorldContext().World();
    if (!World)
        return;
    
    // Determine light color and intensity based on mood and time
    FLinearColor LightColor = FLinearColor::White;
    float Intensity = 3.0f;
    
    if (TimeOfDay == TEXT("night"))
    {
        LightColor = FLinearColor(0.4f, 0.5f, 0.7f);
        Intensity = 1.0f;
    }
    else if (TimeOfDay == TEXT("dawn") || TimeOfDay == TEXT("dusk"))
    {
        LightColor = FLinearColor(1.0f, 0.6f, 0.3f);
        Intensity = 2.0f;
    }
    
    if (Mood == TEXT("dark") || Mood == TEXT("moody"))
    {
        Intensity *= 0.5f;
    }
    else if (Mood == TEXT("bright") || Mood == TEXT("cheerful"))
    {
        Intensity *= 1.5f;
    }
    
    // Create key light
    FVector KeyLightLocation = FVector(-500, -500, 500);
    APointLight* KeyLight = World->SpawnActor<APointLight>(KeyLightLocation, FRotator::ZeroRotator);
    if (KeyLight)
    {
        UPointLightComponent* LightComp = KeyLight->PointLightComponent;
        LightComp->SetIntensity(Intensity * 1000.0f);
        LightComp->SetLightColor(LightColor);
        KeyLight->Tags.Add(TEXT("StoryboardLight"));
    }
    
    UE_LOG(LogStoryboardTo3D, Log, TEXT("Setup lighting - Mood: %s, Time: %s"), *Mood, *TimeOfDay);
}

TArray<FString> UStoryboardPythonBridge::FindAssetsMatching(const FString& SearchTerm)
{
    TArray<FString> Results;
    
    FAssetRegistryModule& AssetRegistryModule = FModuleManager::LoadModuleChecked<FAssetRegistryModule>("AssetRegistry");
    IAssetRegistry& AssetRegistry = AssetRegistryModule.Get();
    
    TArray<FAssetData> AssetData;
    AssetRegistry.GetAllAssets(AssetData);
    
    for (const FAssetData& Asset : AssetData)
    {
        if (Asset.AssetName.ToString().Contains(SearchTerm))
        {
            Results.Add(Asset.GetSoftObjectPath().ToString());
        }
    }
    
    return Results;
}

void UStoryboardPythonBridge::ShowNotification(const FString& Message, bool bSuccess)
{
    FNotificationInfo Info(FText::FromString(Message));
    Info.bFireAndForget = true;
    Info.ExpireDuration = 3.0f;
    Info.bUseSuccessFailIcons = true;
    
    TSharedPtr<SNotificationItem> NotificationItem = FSlateNotificationManager::Get().AddNotification(Info);
    if (NotificationItem.IsValid())
    {
        NotificationItem->SetCompletionState(bSuccess ? SNotificationItem::CS_Success : SNotificationItem::CS_Fail);
    }
}

FString UStoryboardPythonBridge::GetProjectContentDir()
{
    return FPaths::ProjectContentDir();
}

bool UStoryboardPythonBridge::SaveTextureToFile(UTexture2D* Texture, const FString& FilePath)
{
    if (!Texture)
        return false;
    
    // This would require implementation of texture export logic
    // For now, returning false
    return false;
}

UTexture2D* UStoryboardPythonBridge::LoadTextureFromFile(const FString& FilePath)
{
    // This would require implementation of texture import logic
    // For now, returning nullptr
    return nullptr;
}
