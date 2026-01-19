// Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
// This code is proprietary. Unauthorized copying or use is prohibited.
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
                "EditorScriptingUtilities",
                "Json",
                "JsonUtilities",
                "DesktopPlatform",
                "SequencerScripting",
                "LevelSequenceEditor",
                "PythonScriptPlugin"
            }
        );
        
        DynamicallyLoadedModuleNames.AddRange(
            new string[]
            {
            }
        );
    }
}
