// Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
// Licensed under the MIT License. See LICENSE in the repository root.
// Copyright Epic Games, Inc. All Rights Reserved.

#include "StoryboardTo3DCommands.h"

#define LOCTEXT_NAMESPACE "FStoryboardTo3DModule"

void FStoryboardTo3DCommands::RegisterCommands()
{
	UI_COMMAND(OpenPluginWindow, "StoryboardTo3D", "Bring up StoryboardTo3D window", EUserInterfaceActionType::Button, FInputChord());
}

#undef LOCTEXT_NAMESPACE
