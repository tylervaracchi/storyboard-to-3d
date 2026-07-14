// Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
// Licensed under the MIT License. See LICENSE in the repository root.
// Copyright Epic Games, Inc.

#pragma once

#include "CoreMinimal.h"
#include "Modules/ModuleManager.h"

DECLARE_LOG_CATEGORY_EXTERN(LogStoryboardTo3D, Log, All);

class FToolBarBuilder;
class FMenuBuilder;

class FStoryboardTo3DModule : public IModuleInterface
{
public:
    /** IModuleInterface implementation */
    virtual void StartupModule() override;
    virtual void ShutdownModule() override;
    
    /** This function will be bound to Command. */
    void PluginButtonClicked();
    
private:
    void RegisterMenus();
    TSharedRef<class SDockTab> OnSpawnPluginTab(const class FSpawnTabArgs& SpawnTabArgs);
    
private:
    TSharedPtr<class FUICommandList> PluginCommands;
};
