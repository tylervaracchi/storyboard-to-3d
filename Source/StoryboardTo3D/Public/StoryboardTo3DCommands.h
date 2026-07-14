// Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
// Licensed under the MIT License. See LICENSE in the repository root.
// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "Framework/Commands/Commands.h"
#include "StoryboardTo3DStyle.h"

class FStoryboardTo3DCommands : public TCommands<FStoryboardTo3DCommands>
{
public:

	FStoryboardTo3DCommands()
		: TCommands<FStoryboardTo3DCommands>(TEXT("StoryboardTo3D"), NSLOCTEXT("Contexts", "StoryboardTo3D", "StoryboardTo3D Plugin"), NAME_None, FStoryboardTo3DStyle::GetStyleSetName())
	{
	}

	// TCommands<> interface
	virtual void RegisterCommands() override;

public:
	TSharedPtr< FUICommandInfo > OpenPluginWindow;
};