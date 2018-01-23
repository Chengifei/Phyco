/* Copyright 2018 by Yifei Zheng
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * This header encapsulates LLVM optimizer.
 */

#ifndef OPTIMIZE_HPP
#define OPTIMIZE_HPP
// FIXME: these headers are likely to be insufficient
#include <llvm/IR/Module.h>
#include <llvm/Passes/PassBuilder.h>

class optimizer {
    llvm::PassBuilder pb;
    llvm::CGSCCAnalysisManager CGAM;
    llvm::FunctionAnalysisManager FAM;
    llvm::ModuleAnalysisManager MAM;
    llvm::LoopAnalysisManager LAM;
public:
    optimizer(unsigned o_level, unsigned os_level) {
        pb.registerCGSCCAnalyses(CGAM);
        pb.registerModuleAnalyses(MAM);
        pb.registerFunctionAnalyses(FAM);
        pb.crossRegisterProxies(LAM, FAM, CGAM, MAM);
    }
    void operator()(llvm::Module& M) {
        llvm::PassManager<llvm::Module> MPM = pb.buildModuleOptimizationPipeline(llvm::PassBuilder::OptimizationLevel::O2);
        MPM.run(M, MAM);
        MPM = pb.buildModuleSimplificationPipeline(llvm::PassBuilder::OptimizationLevel::O2);
        MPM.run(M, MAM);
    }
};
#endif
