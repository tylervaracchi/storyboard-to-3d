// Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
// Licensed under the MIT License. See LICENSE in the repository root.
// Copyright Epic Games, Inc.

#include "StoryboardTo3D.h"
#include "StoryboardTo3DStyle.h"
#include "StoryboardTo3DCommands.h"
#include "Misc/MessageDialog.h"
#include "ToolMenus.h"
#include "LevelEditor.h"
#include "Widgets/Docking/SDockTab.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Text/STextBlock.h"
#include "Widgets/Input/SButton.h"
#include "Framework/MultiBox/MultiBoxBuilder.h"
#include "Engine/Engine.h"
#include "Interfaces/IPluginManager.h"
#include "Misc/Paths.h"

static const FName StoryboardTo3DTabName("StoryboardTo3D");

#define LOCTEXT_NAMESPACE "FStoryboardTo3DModule"

DEFINE_LOG_CATEGORY(LogStoryboardTo3D);

// Launch the Python UI using the plugin's own install location, wherever it lives.
static void LaunchStoryboardPythonUI()
{
    TSharedPtr<IPlugin> Plugin = IPluginManager::Get().FindPlugin(TEXT("StoryboardTo3D"));
    if (!Plugin.IsValid() || !GEngine)
    {
        UE_LOG(LogStoryboardTo3D, Error, TEXT("StoryboardTo3D plugin not found; cannot launch Python UI."));
        return;
    }
    const FString PythonDir = FPaths::ConvertRelativePathToFull(Plugin->GetBaseDir() / TEXT("Content/Python"));
    const FString Cmd = FString::Printf(
        TEXT("py import sys; p = r'%s'; sys.path.append(p) if p not in sys.path else None; import main; main.show_window()"),
        *PythonDir);
    GEngine->Exec(nullptr, *Cmd);
}

void FStoryboardTo3DModule::StartupModule()
{
    // This code will execute after your module is loaded into memory
    FStoryboardTo3DStyle::Initialize();
    FStoryboardTo3DStyle::ReloadTextures();
    
    FStoryboardTo3DCommands::Register();
    
    PluginCommands = MakeShareable(new FUICommandList);
    
    PluginCommands->MapAction(
        FStoryboardTo3DCommands::Get().OpenPluginWindow,
        FExecuteAction::CreateRaw(this, &FStoryboardTo3DModule::PluginButtonClicked),
        FCanExecuteAction());
    
    UToolMenus::RegisterStartupCallback(FSimpleMulticastDelegate::FDelegate::CreateRaw(this, &FStoryboardTo3DModule::RegisterMenus));
    
    FGlobalTabmanager::Get()->RegisterNomadTabSpawner(StoryboardTo3DTabName, FOnSpawnTab::CreateRaw(this, &FStoryboardTo3DModule::OnSpawnPluginTab))
        .SetDisplayName(LOCTEXT("FStoryboardTo3DTabTitle", "StoryboardTo3D"))
        .SetMenuType(ETabSpawnerMenuType::Hidden);
}

void FStoryboardTo3DModule::ShutdownModule()
{
    // This function may be called during shutdown to clean up your module
    UToolMenus::UnRegisterStartupCallback(this);
    UToolMenus::UnregisterOwner(this);
    
    FStoryboardTo3DStyle::Shutdown();
    FStoryboardTo3DCommands::Unregister();
    
    FGlobalTabmanager::Get()->UnregisterNomadTabSpawner(StoryboardTo3DTabName);
}

TSharedRef<SDockTab> FStoryboardTo3DModule::OnSpawnPluginTab(const FSpawnTabArgs& SpawnTabArgs)
{
    // Launch Python UI with auto-initialization
    LaunchStoryboardPythonUI();
    
    // Return a simple tab with launch button as backup
    return SNew(SDockTab)
        .TabRole(ETabRole::NomadTab)
        [
            SNew(SBox)
            .HAlign(HAlign_Center)
            .VAlign(VAlign_Center)
            .Padding(40)
            [
                SNew(SVerticalBox)
                + SVerticalBox::Slot()
                .AutoHeight()
                .Padding(10)
                [
                    SNew(STextBlock)
                    .Text(FText::FromString(TEXT("StoryboardTo3D Plugin")))
                    .Font(FCoreStyle::GetDefaultFontStyle("Bold", 16))
                ]
                + SVerticalBox::Slot()
                .AutoHeight()
                .Padding(10)
                [
                    SNew(SButton)
                    .Text(FText::FromString(TEXT("Launch Python UI")))
                    .OnClicked_Lambda([]() -> FReply
                    {
                        LaunchStoryboardPythonUI();
                        return FReply::Handled();
                    })
                ]
                + SVerticalBox::Slot()
                .AutoHeight()
                .Padding(10)
                [
                    SNew(STextBlock)
                    .Text(FText::FromString(TEXT("The Python UI should launch automatically.\nIf not, click the button above.")))
                    .Justification(ETextJustify::Center)
                ]
            ]
        ];
}

void FStoryboardTo3DModule::PluginButtonClicked()
{
    // Safety check: Ensure tab manager is valid before invoking
    TSharedPtr<FGlobalTabmanager> TabManager = FGlobalTabmanager::Get();
    if (TabManager.IsValid())
    {
        TabManager->TryInvokeTab(StoryboardTo3DTabName);
    }
    else
    {
        UE_LOG(LogStoryboardTo3D, Error, TEXT("Tab manager is not valid! Cannot invoke StoryboardTo3D tab."));
    }
}

void FStoryboardTo3DModule::RegisterMenus()
{
    // Owner will be used for cleanup in call to UToolMenus::UnregisterOwner
    FToolMenuOwnerScoped OwnerScoped(this);
    
    {
        UToolMenu* Menu = UToolMenus::Get()->ExtendMenu("LevelEditor.MainMenu.Window");
        {
            FToolMenuSection& Section = Menu->FindOrAddSection("WindowLayout");
            Section.AddMenuEntryWithCommandList(FStoryboardTo3DCommands::Get().OpenPluginWindow, PluginCommands);
        }
    }
    
    {
        UToolMenu* ToolbarMenu = UToolMenus::Get()->ExtendMenu("LevelEditor.LevelEditorToolBar.PlayToolBar");
        {
            FToolMenuSection& Section = ToolbarMenu->FindOrAddSection("PluginTools");
            {
                FToolMenuEntry& Entry = Section.AddEntry(FToolMenuEntry::InitToolBarButton(FStoryboardTo3DCommands::Get().OpenPluginWindow));
                Entry.SetCommandList(PluginCommands);
            }
        }
    }
}

#undef LOCTEXT_NAMESPACE

IMPLEMENT_MODULE(FStoryboardTo3DModule, StoryboardTo3D)
