// Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
// Licensed under the MIT License. See LICENSE in the repository root.
// Copyright Epic Games, Inc.

using UnrealBuildTool;

public class StoryboardTo3D : ModuleRules
{
    public StoryboardTo3D(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;
        
        PublicIncludePaths.AddRange(
            new string[] {
            }
        );
        
        PrivateIncludePaths.AddRange(
            new string[] {
            }
        );
        
        PublicDependencyModuleNames.AddRange(
            new string[]
            {
                "Core",
                "CoreUObject",
                "Engine",
                "UnrealEd",
                "LevelSequence",
                "MovieScene",
                "MovieSceneTracks",
                "CinematicCamera"
            }
        );
        
        PrivateDependencyModuleNames.AddRange(
            new string[]
            {
                "Projects",
                "InputCore",
                "EditorSubsystem",
                "ToolMenus",
                "Slate",
                "SlateCore",
                "EditorWidgets",
                "AssetRegistry",
                "ToolWidgets",
                "Json",
                "JsonUtilities",
                "DesktopPlatform",
                "SequencerScripting",
                "LevelSequenceEditor",
                "PythonScriptPlugin",
                "ImageWrapper",
                "ImageCore"
            }
        );
        
        DynamicallyLoadedModuleNames.AddRange(
            new string[]
            {
            }
        );
    }
}
